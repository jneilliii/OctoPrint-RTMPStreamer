# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.server import user_permission
import os
import PIL
import docker
import shlex
import shutil
import subprocess


class rtmpstreamer(octoprint.plugin.StartupPlugin,
                   octoprint.plugin.TemplatePlugin,
                   octoprint.plugin.AssetPlugin,
                   octoprint.plugin.SettingsPlugin,
                   octoprint.plugin.SimpleApiPlugin,
                   octoprint.plugin.EventHandlerPlugin):

    def __init__(self):
        self.client = None
        self.container = None
        self.image = None
        self.ffmpeg = None

        self.frame_rate_default = 5
        self.stream_resolution_default = "640x480"
        self.ffmpeg_cmd_default = (
            "ffmpeg -re -f mjpeg -framerate {frame_rate} -i {webcam_url} {overlay_cmd} "                                                                   # Video input
            "-ar 44100 -ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero "                                               # Audio input
            "-acodec aac -ab 128k "                                                                                        # Audio output
            "-s {stream_resolution} -vcodec h264 -pix_fmt yuv420p -framerate {frame_rate} -g {gop_size} -vb 700k -strict experimental {filter} " # Video output
            "-f flv {stream_url}")                                                                                         # Output stream
        self.overlay_image_default = "jneilliii.png"
        self.docker_image_default = "kolisko/rpi-ffmpeg:latest"
        self.docker_container_default = "RTMPStreamer"

    ##~~ StartupPlugin
    def on_after_startup(self):
        self._logger.info("OctoPrint-RTMPStreamer loaded! Checking stream status.")
        if self._settings.get(["use_docker"]):
            self._get_image()
        self._check_stream()
        if self._settings.get(["auto_start_on_power_up"]) and self._settings.get(["stream_url"]) != "":
            self._logger.info("Auto starting stream on start up.")
            self._start_stream()

    ##~~ TemplatePlugin
    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

    def get_template_vars(self):
        return dict(
            frame_rate_default = self.frame_rate_default,
            ffmpeg_cmd_default = self.ffmpeg_cmd_default,
            docker_image_default = self.docker_image_default,
            docker_container_default = self.docker_container_default
        )

    ##~~ SettingsPlugin
    def get_settings_defaults(self):
        return dict(
            # put your plugin's default settings here
            view_url = "",
            stream_url = "",
            stream_resolution = self.stream_resolution_default,
            use_overlay = True,
            use_dynamic_overlay = False,
            overlay_style = "wm_br",
            overlay_padding = 10,
            overlay_file = self._basefolder + "/static/img/" + self.overlay_image_default,
            streaming = False,
            auto_start = False,
            auto_start_on_power_up=False,
            use_docker = False,
            docker_image = self.docker_image_default,
            docker_container = self.docker_container_default,
            ffmpeg_cmd = self.ffmpeg_cmd_default,
            frame_rate = self.frame_rate_default,

            # Default values
            frame_rate_default = self.frame_rate_default,
            ffmpeg_cmd_default = self.ffmpeg_cmd_default,
            docker_image_default = self.docker_image_default,
            docker_container_default = self.docker_container_default
        )

    def get_settings_restricted_paths(self):
        return dict(admin=[["stream_url"]])

    ##~~ AssetPlugin
    def get_assets(self):
        return dict(
            js=["js/rtmpstreamer.js"],
            css=["css/rtmpstreamer.css"]
        )

    ##-- EventHandlerPlugin
    def on_event(self, event, payload):
        if event == "PrintStarted" and self._settings.get(["auto_start"]):
            self._start_stream()

        if event in ["PrintDone", "PrintCancelled"] and self._settings.get(["auto_start"]):
            self._stop_stream()

    ##-- Utility Functions
    def _get_client(self):
        self.client = docker.from_env()
        try:
            self.client.ping()
        except Exception as e:
            self._logger.error("Docker not responding: " + str(e))
            self.client = None

    def _get_image(self):
        self._get_client()
        if self.client:
            try:
                self.image = self.client.images.get(self._settings.get(["docker_image"]))
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
            if self.ffmpeg:
                self.container = self.ffmpeg
            else:
                self.container = self.ffmpeg = None

    ##~~ SimpleApiPlugin
    def get_api_commands(self):
        return dict(startStream=[], stopStream=[], checkStream=[])

    def on_api_command(self, command, data):
        if not user_permission.can():
            from flask import make_response
            return make_response("Insufficient rights", 403)

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

    ##~~ General Functions
    def _start_stream(self):
        if self._settings.global_get(["webcam", "stream"]).startswith("/"):
            self._plugin_manager.send_plugin_message(self._identifier, dict(
                error="Webcam stream url is incorrect.  Please configure OctoPrint's Webcam & Timelapse url to include fullly qualified url, like http://192.168.0.2/webcam/?action=stream",
                status=True, streaming=False))
            return

        if not self.container:
            overlay_cmds = dict(
                fs = "-filter_complex \"[0:v]scale={stream_width}:{stream_height}[base]; [1:v][base]scale2ref=iw:-1[over][base]; [base][over]overlay=0:0\"",
                wm_br = "-filter_complex \"[0:v]scale={stream_width}:{stream_height}[base]; [base][1:v] overlay=({stream_width} - {overlay_width} - {overlay_padding}):({stream_height} - {overlay_height} - {overlay_padding})\"",
                wm_bl = "-filter_complex \"[0:v]scale={stream_width}:{stream_height}[base]; [base][1:v] overlay={overlay_padding}:({stream_height} - {overlay_height} - {overlay_padding})\"",
                wm_tr = "-filter_complex \"[0:v]scale={stream_width}:{stream_height}[base]; [base][1:v] overlay=({stream_width} - {overlay_width} - {overlay_padding}):{overlay_padding}\"",
                wm_tl = "-filter_complex \"[0:v]scale={stream_width}:{stream_height}[base]; [base][1:v] overlay={overlay_padding}:{overlay_padding}\""
            )
            filter_str = ""
            filters = []
            if self._settings.global_get(["webcam", "flipH"]):
                filters.append("hflip")
            if self._settings.global_get(["webcam", "flipV"]):
                filters.append("vflip")
            if self._settings.global_get(["webcam", "rotate90"]):
                filters.append("transpose=cclock")
            if len(filters):
                filter_str = "-filter:v {}".format(",".join(filters))
            gop_size = int(self._settings.get(["frame_rate"])) * 2
            overlay_cmd = ""
            if self._settings.get(["use_overlay"]):
                if os.path.isfile(self._settings.get(["overlay_file"])):
                    shutil.copy(self._settings.get(["overlay_file"]), "/tmp/overlay.png")
                if os.path.isfile("/tmp/overlay.png"):
                    overlay = PIL.Image.open("/tmp/overlay.png")
                    overlay_width, overlay_height = overlay.size
                    #ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 http://127.0.0.1/webcam/?action=stream
                    stream_width, stream_height = self._settings.get(["stream_resolution"]).split("x")
                    # Substitute vars in overlay command
                    overlay_cmd = overlay_cmds[self._settings.get(["overlay_style"])].format(
                        stream_width = stream_width,
                        stream_height = stream_height,
                        overlay_width = overlay_width,
                        overlay_height = overlay_height,
                        overlay_padding = self._settings.get(["overlay_padding"]))
                if self._settings.get(["use_dynamic_overlay"]):
                    overlay_cmd = "-pattern_type glob -loop 2 -r 1 -i \"/tmp/overlay*.png\" " + overlay_cmd
                else:
                    overlay_cmd = "-i /tmp/overlay.png " + overlay_cmd
            # Substitute vars in ffmpeg command
            stream_cmd = self._settings.get(["ffmpeg_cmd"]).format(
                overlay_cmd = overlay_cmd,
                webcam_url = self._settings.global_get(["webcam", "stream"]),
                stream_url = self._settings.get(["stream_url"]),
                frame_rate = self._settings.get(["frame_rate"]),
                stream_resolution = self._settings.get(["stream_resolution"]),
                gop_size = gop_size,
                filter = filter_str)
            try:
                if self._settings.get(["use_docker"]):
                    self._logger.info("Launching docker container '" + self._settings.get(["docker_container"]) + "':\n" + "|  " + stream_cmd)
                    self._get_client()
                    self.container = self.client.containers.run(
                        self._settings.get(["docker_image"]),
                        command = stream_cmd,
                        detach = True,
                        privileged = False,
                        devices = ["/dev/vchiq"],
                        volumes = {"/tmp/overlay.png": {"bind": "/tmp/overlay.png", "mode": "ro"}},
                        name = self._settings.get(["docker_container"]),
                        auto_remove = True,
                        network_mode = "host")
                else:
                    self._logger.info("Launching ffmpeg locally:\n" + "|  " + stream_cmd)
                    cmd = shlex.split(stream_cmd, posix=True)
                    self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
                    self._logger.info("Stream ffmpeg pid {}".format(self.ffmpeg.pid))
            except Exception as e:
                self._logger.error(str(e))
                self._plugin_manager.send_plugin_message(self._identifier, dict(error=str(e),status=True,streaming=False))
            else:
                self._logger.info("Stream started successfully")
                self._plugin_manager.send_plugin_message(self._identifier, dict(success="Stream started",status=True,streaming=True))
                if self._settings.get(["use_dynamic_overlay"]):
                    self._build_overlay()

    def _build_overlay(self):
        # FIXME: start dynamic image update process, should be a background loop
        # that stops with the stream
        return

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
                            self._plugin_manager.send_plugin_message(self._identifier, dict(error=err,status=True,streaming=False))
                    self.ffmpeg.terminate()
                    self.ffmpeg.kill()
            except Exception as e:
                self._logger.error(str(e))
                self._plugin_manager.send_plugin_message(self._identifier, dict(error=str(e),status=True,streaming=False))
            else:
                self.ffmpeg = None
                self.container = None
                self._logger.info("Stream stopped successfully")
                self._plugin_manager.send_plugin_message(self._identifier, dict(success="Stream stopped",status=True,streaming=False))
        else:
            self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=False))

    def _check_stream(self):
        self._get_container()
        if self.container:
            self._logger.info("%s is streaming " % self.container.name)
            self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=True))
        else:
            self._logger.info("stream is inactive ")
            self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=False))

    ##~~ Softwareupdate hook
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


__plugin_name__ = "RTMP Streamer"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = rtmpstreamer()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
