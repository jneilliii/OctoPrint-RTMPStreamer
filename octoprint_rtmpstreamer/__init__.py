# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import octoprint.util
import octoprint.filemanager.storage
from flask_babel import gettext
from octoprint.access import ADMIN_GROUP
from octoprint.access.permissions import Permissions
from octoprint.server import user_permission
import logging
import os
import io
import sys
import tempfile
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
import urllib
from docker import from_env as docker_from_env
from docker.errors import ImageNotFound, APIError
import shlex
import shutil
import subprocess
import flask
import re

import octoprint.server.util.flask
from octoprint.server import admin_permission, NO_CONTENT


class rtmpstreamer(octoprint.plugin.BlueprintPlugin,
                   octoprint.plugin.StartupPlugin,
                   octoprint.plugin.TemplatePlugin,
                   octoprint.plugin.AssetPlugin,
                   octoprint.plugin.SettingsPlugin,
                   octoprint.plugin.SimpleApiPlugin,
                   octoprint.plugin.EventHandlerPlugin):

    def __init__(self):
        self._logger = logging.getLogger(__name__)

        self.tmpdir = tempfile.gettempdir()
        if sys.platform == "darwin":
            self.platform = "darwin"
        elif sys.platform == "win32":
            self.platform = "win32"
            # glob is only availabe on POSIX systems
            self.use_dynamic_overlay = False
        else:
            self.platform = "linux"
            try:
                with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
                    if 'raspberry pi' in m.read().lower():
                        self.platform = "pi"
                        self.tmpdir = "/dev/shm"
            except Exception:
                pass

        self.client = None
        self.container = None
        self.image = None
        self.ffmpeg = None
        self.dynamicInfo = None

        self.frame_rate_default = 5
        self.stream_resolution_default = "640x480"

        self.ffmpeg_cmd_default = (
            "{ffmpeg} -re -f mjpeg -framerate {frame_rate} -i {webcam_url} {filter} "  # Video input
            "-f lavfi -i anullsrc " # Audio input
            "-acodec aac -ab 128k "  # Audio output
            "-s {stream_resolution} -vcodec {videocodec} -threads {threads} -pix_fmt yuv420p -framerate {frame_rate} -g {gop_size} -vb {bitrate} -strict experimental "  # Video output
            "-f flv {stream_url}")  # Output stream
        self.overlay_image_default = "jneilliii.png"
        self.docker_image_default = "kolisko/rpi-ffmpeg:latest"
        self.docker_container_default = "RTMPStreamer"

    # ~~ BluePrint API mixin

    @octoprint.plugin.BlueprintPlugin.route("/rtmpstreamer_upload", methods=["POST"])
    @octoprint.server.util.flask.restricted_access
    @Permissions.PLUGIN_RTMPSTREAMER_CONTROL.require(403)
    def upload_file(self):
        input_name = "file"
        input_upload_path = input_name + "." + self._settings.global_get(["server", "uploads", "pathSuffix"])
        input_upload_file = input_name + ".name"

        if input_upload_path in flask.request.values:
            uploaded_file = flask.request.values[input_upload_path]
            file = os.path.basename(flask.request.values[input_upload_file])

            try:
                shutil.move(os.path.abspath(uploaded_file), os.path.join(self.get_plugin_data_folder(), file))
            except:
                error_message = "Error while copying the uploaded file"
                self._logger.exception(error_message)
                return flask.make_response(error_message, 500)
        else:
            return flask.make_response("No file given in upload.", 400)

        return flask.jsonify(self.getImageList())

    # ~~ StartupPlugin mixin

    def on_startup(self, host, port):
        # setup our custom logger
        from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
        logging_handler = CleaningTimedRotatingFileHandler(self._settings.get_plugin_logfile_path(postfix="engine"),
                                                           when="D", backupCount=3)
        logging_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logging_handler.setLevel(logging.DEBUG)

        self._logger.addHandler(logging_handler)
        self._logger.propagate = False

    def on_after_startup(self):
        self._logger.info("OctoPrint-RTMPStreamer loaded! Checking stream status.")
        shutil.copy(os.path.join(self._basefolder, "static", "img", self.overlay_image_default),
                    self.get_plugin_data_folder())
        if self._settings.get(["use_docker"]):
            self._get_image()
        self._check_stream()
        if self._settings.get(["auto_start_on_power_up"]) and self._settings.get(["stream_url"]) != "":
            self._logger.info("Auto starting stream on start up.")
            self._start_stream()

        if self.platform == "win32":
            # glob is only availabe on POSIX systems
            self._logger.info("Forcing dynamic overlays to off as we aren't posix")
            self._settings.set_boolean(["use_dynamic_overlay"], False)

    # ~~ TemplatePlugin mixin

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=True)]

    def get_template_vars(self):
        return dict(
            frame_rate_default=self.frame_rate_default,
            ffmpeg_cmd_default=self.ffmpeg_cmd_default,
            docker_image_default=self.docker_image_default,
            docker_container_default=self.docker_container_default,
            overlay_file_default=self.overlay_image_default,
            plugin_version=self._plugin_version
        )

    # ~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return dict(
            platform=self.platform,

            # put your plugin's default settings here
            view_url="",
            stream_url="",
            stream_resolution=self.stream_resolution_default,
            use_overlay=True,
            use_dynamic_overlay=False,
            dynamic_overlay_interval=2,
            dynamic_layout=[],
            overlay_style="wm_br",
            overlay_padding=10,
            overlay_file=self.overlay_image_default,
            overlay_files=self.getImageList(),
            include_thumb=False,
            thumbw=300,
            thumbh=300,
            thumbx=10,
            thumby=10,
            streaming=False,
            auto_start=False,
            auto_start_on_power_up=False,
            use_docker=False,
            docker_image=self.docker_image_default,
            docker_container=self.docker_container_default,
            docker_pull=False,
            ffmpeg_cmd=self.ffmpeg_cmd_default,
            frame_rate=self.frame_rate_default,
            stream_bitrate="400k",
            ffmpeg_threads=1,
            ffmpeg_codec="libx264",

            # Default values
            frame_rate_default=self.frame_rate_default,
            ffmpeg_cmd_default=self.ffmpeg_cmd_default,
            docker_image_default=self.docker_image_default,
            docker_container_default=self.docker_container_default,
            overlay_file_default=self.overlay_image_default,
            plugin_version=self._plugin_version
        )

    def get_settings_restricted_paths(self):
        return dict(admin=[["stream_url"]])

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        if self._settings.get(["use_docker"]):
            # If using docker, check image after settings update
            self._get_image()

    # ~~ AssetPlugin mixin

    def get_assets(self):
        return dict(
            js=["js/rtmpstreamer.js"],
            css=["css/rtmpstreamer.css"]
        )

    # -- EventHandlerPlugin

    def on_event(self, event, payload):
        if event == "PrintStarted" and self._settings.get(["auto_start"]):
            self._start_stream()

        if event in ["PrintDone", "PrintCancelled"] and self._settings.get(["auto_start"]):
            self._stop_stream()

    # -- Utility Functions

    def _get_client(self):
        self.client = docker_from_env()
        try:
            self.client.ping()
            self._logger.debug("Received ping from Docker")
        except Exception as e:
            self._logger.error("Docker not responding: " + str(e))
            self.client = None

    def _get_image(self):
        self._get_client()
        if self.client:
            try:
                _docker_image = self._settings.get(["docker_image"])
                self.image = self.client.images.get(_docker_image)
            except ImageNotFound as e:
                self._logger.warning("Docker image " + _docker_image + " not found")
                if self._settings.get(["docker_pull"]):
                    self._pull_image()
            except APIError as e:
                self._logger.error("Docker API error:")
                self._logger.error(str(e))
            except Exception as e:
                self._logger.error(str(e))
                self._logger.error("Please read installation instructions!")
                self.image = None

    def _get_container(self):
        if self._settings.get(["use_docker"]):
            self._get_client()
            if self.client:
                try:
                    self.container = self.client.containers.get(self._settings.get(["docker_container"]))
                except Exception as e:
                    self.client = None
                    self.container = None
        else:
            if self.ffmpeg and not self.ffmpeg.returncode:
                self.container = self.ffmpeg
            else:
                self.container = self.ffmpeg = None

    def _pull_image(self):
        self._get_client()
        if self.client:
            _docker_image = self._settings.get(["docker_image"])
            try:
                self._logger.debug("Attempting to pull image " + _docker_image)
                self.client.images.pull(_docker_image)
                self._logger.info("Docker image " + _docker_image + " was pulled successfully")
            except Exception as e:
                self._logger.error("Unknown error: " + e)
        else:
            self._logger.error("Unable to connect to Docker")

    # ~~ SimpleApiPlugin
    def get_api_commands(self):
        return dict(startStream=[], stopStream=[], checkStream=[], removeImage=[], updateImages=[])

    def on_api_command(self, command, data):
        if not Permissions.PLUGIN_RTMPSTREAMER_CONTROL.can():
            return flask.make_response("Insufficient rights", 403)

        if command == 'startStream':
            self._logger.info("Start stream command received.")
            self._start_stream()
            return
        if command == 'stopStream':
            self._logger.info("Stop stream command received.")
            self._stop_stream()
        if command == 'checkStream':
            self._logger.info("Checking stream status.")
            self._check_stream()

    def on_api_get(self, request):
        if request.args.get("removeImage"):
            self.removeImage(request.args.get("removeImage"))
            return flask.jsonify(self.getImageList())
        if request.args.get("updateImages"):
            return flask.jsonify(self.getImageList())

    # ~~ General Functions

    def _start_stream(self):
        if not self._settings.global_get(["webcam", "ffmpeg"]) and not self._settings.get(["use_docker"]):
            self._plugin_manager.send_plugin_message(self._identifier, dict(
                error="Path to FFMPEG not set.  Please configure OctoPrint's Webcam & Timelapse path, or use docker",
                status=True, streaming=False))
            return
        if not self._settings.global_get(["webcam", "stream"]):
            self._plugin_manager.send_plugin_message(self._identifier, dict(
                error="No Webcam stream url.  Please configure OctoPrint's Webcam & Timelapse url",
                status=True, streaming=False))
            return
        elif self._settings.global_get(["webcam", "stream"]).startswith("/"):
            self._logger.info("Webcam stream url starts with a /, assuming localhost.")
            # FIXME Should have a check for https here?
            webcamstream = "http://127.0.0.1" + self._settings.global_get(["webcam", "stream"])
        else:
            webcamstream = self._settings.global_get(["webcam", "stream"])

        if not self.container:
            overlay_cmds = dict(
                no="-filter_complex \"[0:v]{filter}scale={stream_width}:{stream_height}[base]",
                fs="-filter_complex \"[0:v]{filter}scale={stream_width}:{stream_height}[base]; [1:v][base]scale2ref=iw:-1[over][base]; [base][over]overlay=0:0\"",
                wm_br="-filter_complex \"[0:v]{filter}scale={stream_width}:{stream_height}[base]; [base][1:v]overlay=({stream_width} - {overlay_width} - {overlay_padding}):({stream_height} - {overlay_height} - {overlay_padding})\"",
                wm_bl="-filter_complex \"[0:v]{filter}scale={stream_width}:{stream_height}[base]; [base][1:v]overlay={overlay_padding}:({stream_height} - {overlay_height} - {overlay_padding})\"",
                wm_tr="-filter_complex \"[0:v]{filter}scale={stream_width}:{stream_height}[base]; [base][1:v]overlay=({stream_width} - {overlay_width} - {overlay_padding}):{overlay_padding}\"",
                wm_tl="-filter_complex \"[0:v]{filter}scale={stream_width}:{stream_height}[base]; [base][1:v]overlay={overlay_padding}:{overlay_padding}\""
            )
            filter_str = ""
            filters = []
            if self._settings.global_get_boolean(["webcam", "flipH"]) or self._settings.global_get_boolean(["plugins", "classicwebcam", "flipH"]):
                filters.append("hflip")
            if self._settings.global_get_boolean(["webcam", "flipV"]) or self._settings.global_get_boolean(["plugins", "classicwebcam", "flipV"]):
                filters.append("vflip")
            if self._settings.global_get_boolean(["webcam", "rotate90"]) or self._settings.global_get_boolean(["plugins", "classicwebcam", "rotate90"]):
                filters.append("transpose=cclock")
            if len(filters):
                filter_str = "{},".format(",".join(filters))
            gop_size = int(self._settings.get(["frame_rate"])) * 2
            overlay_cmd = ""
            overlay_width = overlay_height = overlay_padding = 0
            if self._settings.get(["use_overlay"]):
                if os.path.isfile(os.path.join(self.get_plugin_data_folder(), self._settings.get(["overlay_file"]))):
                    if self._settings.get(["use_dynamic_overlay"]):
                        self._build_overlay()
                    else:
                        shutil.copy(os.path.join(self.get_plugin_data_folder(), self._settings.get(["overlay_file"])),
                                    os.path.join(self.tmpdir, "overlay.png"))
                if os.path.isfile(os.path.join(self.tmpdir, "overlay.png")):
                    overlay = Image.open(os.path.join(self.tmpdir, "overlay.png"))
                    overlay_width, overlay_height = overlay.size
                    # FIXME is this a sane test? what about with docker?
                    # test stream before use, won't work unless ffprobe is available, ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 webcamstream
                stream_width, stream_height = self._settings.get(["stream_resolution"]).split("x")
                # Substitute vars in overlay command
                if self._settings.get(["use_dynamic_overlay"]):
                    overlay_style = "fs"
                elif not self._settings.get(["use_overlay"]):
                    overlay_style = "no"
                else:
                    overlay_style = self._settings.get(["overlay_style"])
                overlay_cmd = overlay_cmds[overlay_style].format(
                    filter=filter_str,
                    stream_width=stream_width,
                    stream_height=stream_height,
                    overlay_width=overlay_width,
                    overlay_height=overlay_height,
                    overlay_padding=self._settings.get(["overlay_padding"]))
                if self._settings.get(["use_dynamic_overlay"]):
                    overlay_cmd = "-pattern_type glob -loop 1 -r 30 -i \"" + os.path.join(self.tmpdir, "overlay") + "*.png\" " + overlay_cmd
                elif self._settings.get(["use_overlay"]):
                    overlay_cmd = "-i " + os.path.join(self.tmpdir, "overlay.png") + " " + overlay_cmd
            ffmpeg_cli = "ffmpeg"
            if self._settings.global_get(["webcam", "ffmpeg"]):
                ffmpeg_cli = self._settings.global_get(["webcam", "ffmpeg"]).replace("\\", "/")
            # Substitute vars in ffmpeg command
            stream_cmd = self._settings.get(["ffmpeg_cmd"]).format(
                ffmpeg=ffmpeg_cli.replace("\\", "/"), # use replace to handle for windows pathing back slash
                filter=overlay_cmd.replace("\\", "/"), # use replace to handle for windows pathing back slash
                webcam_url=webcamstream,
                stream_url=self._settings.get(["stream_url"]),
                frame_rate=self._settings.get(["frame_rate"]),
                bitrate=self._settings.get(["stream_bitrate"]),
                threads=self._settings.get(["ffmpeg_threads"]),
                videocodec=self._settings.get(["ffmpeg_codec"]),
                stream_resolution=self._settings.get(["stream_resolution"]),
                gop_size=gop_size)
            try:
                if self._settings.get(["use_docker"]):
                    self._logger.info("Launching docker container '" + self._settings.get(
                        ["docker_container"]) + "':\n" + "|  " + stream_cmd)
                    self._get_client()
                    # FIXME testing if this is required devices = ["/dev/vchiq"],
                    # This would continue if _get_client() above does not return client
                    if not self.client:
                        return
                    self._get_image()
                    self.container = self.client.containers.run(
                        self._settings.get(["docker_image"]),
                        command=stream_cmd,
                        detach=True,
                        privileged=False,
                        volumes={
                            os.path.join(self.tmpdir, "overlay.png"): {"bind": os.path.join(self.tmpdir, "overlay.png"),
                                                                       "mode": "ro"}},
                        name=self._settings.get(["docker_container"]),
                        auto_remove=True,
                        network_mode="host")
                else:
                    self._logger.info("Launching ffmpeg locally:\n" + "|  " + stream_cmd)
                    cmd = shlex.split(stream_cmd, posix=True)
                    if self._settings.get(["debug_ffmpeg"]):
                        stdout_loc = self._logger.handlers[0].stream
                        stderr_loc = self._logger.handlers[0].stream
                    else:
                        stdout_loc = subprocess.DEVNULL
                        stderr_loc = subprocess.DEVNULL
                    self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=stderr_loc, stdout=stdout_loc)
                    self._logger.info("Stream ffmpeg pid {}".format(self.ffmpeg.pid))
            except Exception as e:
                self._logger.error(str(e))
                self._plugin_manager.send_plugin_message(self._identifier,
                                                         dict(error=str(e), status=True, streaming=False))
            else:
                self._logger.info("Stream started successfully")
                self._plugin_manager.send_plugin_message(self._identifier,
                                                         dict(success="Stream started", status=True, streaming=True))
                if self._settings.get(["use_dynamic_overlay"]):
                    self._logger.info("Starting dynamic overlay loop")
                    self.dynamicInfo = octoprint.util.RepeatedTimer(
                        int(self._settings.get(["dynamic_overlay_interval"])), self._build_overlay)
                    self.dynamicInfo.start()

    def _build_overlay(self):
        # Get the current printer data
        current_data = self._printer.get_current_data()
        self._logger.debug(current_data)
        current_job = self._printer.get_current_job()
        self._logger.debug(current_job)
        current_temps = self._printer.get_current_temperatures()

        # name, path, size, origin, date
        fileInfo = current_data["job"]["file"]
        filename = "None Loaded"
        if fileInfo["name"]:
            filename = re.sub(r"\.gcod?e?$", "", fileInfo["name"], flags=re.IGNORECASE)

        estimatedPrintTime = current_data["job"]["estimatedPrintTime"]

        # completion, filepos, printTime, printTimeLeft, printTimeOrigin
        jobInfo = current_data["progress"]

        # [tooln, bed, chamber][actual, target]
        temps = current_temps

        overlay_style = self._settings.get(["overlay_style"])
        padding = self._settings.get(["overlay_padding"])
        if overlay_style == "fs":
            img = Image.open(os.path.join(self.get_plugin_data_folder(), self._settings.get(["overlay_file"])))
        else:
            watermark = Image.open(os.path.join(self.get_plugin_data_folder(), self._settings.get(["overlay_file"])))
            wm_w, wm_h = watermark.size
            img_w, img_h = self._settings.get(["stream_resolution"]).split("x")
            img = Image.new('RGBA', (int(img_w), int(img_h)), (0, 0, 0, 0))
            img_w, img_h = img.size
            if overlay_style == "wm_br":
                img.paste(watermark, ((img_w - wm_w - padding), (img_h - wm_h - padding)))
            elif overlay_style == "wm_bl":
                img.paste(watermark, ((padding), (img_h - wm_h - padding)))
            elif overlay_style == "wm_tr":
                img.paste(watermark, ((img_w - wm_w - padding), (padding)))
            elif overlay_style == "wm_tl":
                img.paste(watermark, (padding, padding))

        if 'prusaslicerthumbnails' in self._plugin_manager.plugins and self._settings.get_boolean(["include_thumb"]):
            thumbfile = os.path.join(self._settings.global_get_basefolder("data"), "prusaslicerthumbnails", filename + ".png")
            if os.path.exists(thumbfile):
                thumb = Image.open(thumbfile)
                th_w = self._settings.get(["thumbw"])
                th_h = self._settings.get(["thumbh"])
                newsize = (int(th_w), int(th_h))
                thumb = thumb.resize(newsize)
                th_x = int(self._settings.get(["thumbx"]))
                th_y = int(self._settings.get(["thumby"]))
                img.paste(thumb, (th_x, th_y), thumb)

        draw = ImageDraw.Draw(img)

        dynamicLayout = self._settings.get(["dynamic_layout"])

        for quadrant in dynamicLayout:
            fontname = "times-ro.ttf"
            if quadrant["font"]:
                fontname = quadrant["font"]
            fontsize = 24
            if quadrant["size"]:
                fontsize = int(quadrant["size"])

            try:
                font = ImageFont.truetype(os.path.join(self._basefolder, "static", "fonts", fontname), fontsize)
            except Exception as e:
                self._logger.error("{} font not found: {}".format(fontname, e))
                font = ImageFont.truetype(os.path.join(self._basefolder, "static", "fonts", "times.ttf"), fontsize)

            loc_x = 10
            loc_y = 10
            if quadrant["posx"]:
                loc_x = int(quadrant["posx"])
            if quadrant["posy"]:
                loc_y = int(quadrant["posy"])
            txt = "N/A"
            if quadrant["text"]:
                txt = quadrant["text"]
            color = (0, 0, 0)
            if quadrant["color"]:
                h = quadrant["color"].lstrip("#")
                color = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

            txtval = txt.format(
                filename=filename,
                estimatedprinttime=self.convertSeconds(int(estimatedPrintTime)) if estimatedPrintTime else "...",
                percdone="{:.2f}".format(jobInfo["completion"]) if jobInfo["completion"] else 0,
                printtime=self.convertSeconds(int(jobInfo["printTime"])) if jobInfo["printTime"] else "...",
                timeleft=self.convertSeconds(int(jobInfo["printTimeLeft"])) if jobInfo["printTimeLeft"] else "...",
                bedtemp=temps["bed"]["actual"] if "bed" in temps else 0,
                bedtarget=temps["bed"]["target"] if "bed" in temps else 0,
                chambertemp=temps["chamber"]["actual"] if "chamber" in temps else 0,
                chambertarget=temps["chamber"]["target"] if "chamber" in temps else 0,
                tool0temp=temps["tool0"]["actual"] if "tool0" in temps else 0,
                tool0target=temps["tool0"]["target"] if "tool0" in temps else 0,
                tool1temp=temps["tool1"]["actual"] if "tool1" in temps else 0,
                tool1target=temps["tool1"]["target"] if "tool1" in temps else 0,
                tool2temp=temps["tool2"]["actual"] if "tool2" in temps else 0,
                tool2target=temps["tool2"]["target"] if "tool2" in temps else 0,
                tool3temp=temps["tool3"]["actual"] if "tool3" in temps else 0,
                tool3target=temps["tool3"]["target"] if "tool3" in temps else 0,
                tool4temp=temps["tool4"]["actual"] if "tool4" in temps else 0,
                tool4target=temps["tool4"]["target"] if "tool4" in temps else 0)

            draw.text((loc_x, loc_y), txtval, color, font=font)

        img.save(os.path.join(self.tmpdir, "tmp_overlay.png"), "PNG")
        # this is important, ffmpeg only works if you use move
        shutil.move(os.path.join(self.tmpdir, "tmp_overlay.png"), os.path.join(self.tmpdir, "overlay.png"))

    def _stop_stream(self):
        self._get_container()
        if self.container:
            try:
                if self._settings.get(["use_docker"]):
                    self._logger.info("Stream stopping docker")
                    self.container.stop()
                else:
                    self._logger.info("Stream stopping ffmpeg pid {}".format(self.ffmpeg.pid))
                    if self.ffmpeg.returncode:
                        out, err = self.ffmpeg.communicate()
                        if err:
                            self._logger.error("FFMPEG Error: {}".format(err))
                            self._plugin_manager.send_plugin_message(self._identifier,
                                                                     dict(error=err, status=True, streaming=False))
                    self.ffmpeg.terminate()

                if self._settings.get(["use_dynamic_overlay"]):
                    self._logger.info("Stopping dynamic overlay loop")
                    self.dynamicInfo.cancel()
                    self.dynamicInfo = None
            except Exception as e:
                self._logger.error(str(e))
                self._plugin_manager.send_plugin_message(self._identifier,
                                                         dict(error=str(e), status=True, streaming=False))
            else:
                self.ffmpeg = None
                self.container = None
                self._logger.info("Stream stopped successfully")
                self._plugin_manager.send_plugin_message(self._identifier,
                                                         dict(success="Stream stopped", status=True, streaming=False))
        else:
            self._plugin_manager.send_plugin_message(self._identifier, dict(status=True, streaming=False))

    def _check_stream(self):
        self._get_container()
        if self.container:
            if self._settings.get(["use_docker"]):
                self._logger.info("%s is streaming " % self.container.name)
            else:
                self._logger.info("ffmpeg pid %s is streaming " % self.ffmpeg.pid)
            self._plugin_manager.send_plugin_message(self._identifier, dict(status=True, streaming=True))
        else:
            self._logger.info("stream is inactive ")
            self._plugin_manager.send_plugin_message(self._identifier, dict(status=True, streaming=False))

    # ~~ Access Permissions Hook

    def get_additional_permissions(self, *args, **kwargs):
        return [
            dict(key="CONTROL",
                 name="Control Stream",
                 description=gettext("Allows control of the stream."),
                 roles=["admin"],
                 dangerous=True,
                 default_groups=[ADMIN_GROUP])
        ]

    # ~~ Softwareupdate hook

    def get_update_information(self):
        return dict(
            rtmpstreamer=dict(
                displayName="RTMP Streamer",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="jneilliii",
                repo="OctoPrint-RTMPStreamer",
                current=self._plugin_version,
                stable_branch=dict(
                    name="Stable", branch="master", comittish=["master"]
                ),
                prerelease_branches=[
                    dict(
                        name="Release Candidate",
                        branch="rc",
                        comittish=["rc", "master"],
                    )
                ],

                # update method: pip
                pip="https://github.com/jneilliii/OctoPrint-RTMPStreamer/archive/{target_version}.zip"
            )
        )

    def convertSeconds(self, seconds):
        h = seconds // (60 * 60)
        m = (seconds - h * 60 * 60) // 60
        s = seconds - (h * 60 * 60) - (m * 60)

        return "{:02}:{:02}:{:02}".format(h, m, s)

    def getImageList(self):
        return [f for f in os.listdir(self.get_plugin_data_folder()) if
                os.path.isfile(os.path.join(self.get_plugin_data_folder(), f))]

    def removeImage(self, file):
        if os.path.exists(os.path.join(self.get_plugin_data_folder(), file)):
            os.remove(os.path.join(self.get_plugin_data_folder(), file));


__plugin_name__ = "RTMP Streamer"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = rtmpstreamer()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.access.permissions": __plugin_implementation__.get_additional_permissions,
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
