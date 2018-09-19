# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.server import user_permission
import docker

class rtmpstreamer(octoprint.plugin.StartupPlugin,
				octoprint.plugin.TemplatePlugin,
				octoprint.plugin.AssetPlugin,
                octoprint.plugin.SettingsPlugin,
				octoprint.plugin.SimpleApiPlugin,
				octoprint.plugin.EventHandlerPlugin):
	
	def __init__(self):
		self.client = docker.from_env()
		self.container = None
	
	##~~ StartupPlugin
	def on_after_startup(self):
		self._logger.info("OctoPrint-RTMPStreamer loaded! Checking stream status.")
		try:
			self.container = self.client.containers.get('RTMPStreamer')
			self._logger.info("%s is streaming " % self.container.name)
			self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=True))
		except Exception, e:
			self._logger.error(str(e))
			self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=False))
			
		if self._settings.get(["auto_start_on_power_up"]) and self._settings.get(["stream_url"]) != "":
			self._logger.info("Auto starting stream on start up.")
			self.startStream()
	
	##~~ TemplatePlugin
	def get_template_configs(self):
		return [dict(type="settings",custom_bindings=False)]
		
	##~~ AssetPlugin
	def get_assets(self):
		return dict(
			js=["js/rtmpstreamer.js"],
			css=["css/rtmpstreamer.css"]
		)
		
	##-- EventHandlerPlugin	
	def on_event(self, event, payload):
		if event == "PrintStarted" and self._settings.get(["auto_start"]):
			self.startStream()
			
		if event in ["PrintDone","PrintCancelled"] and self._settings.get(["auto_start"]):
			self.stopStream()
		
	##~~ SettingsPlugin
	def get_settings_defaults(self):
		return dict(view_url="",stream_url="",stream_resolution="640x480",stream_framerate="5",streaming=False,auto_start=False,auto_start_on_power_up=False)
		
	##~~ SimpleApiPlugin	
	def get_api_commands(self):
		return dict(startStream=[],stopStream=[],checkStream=[])
		
	def on_api_command(self, command, data):
		if not user_permission.can():
			from flask import make_response
			return make_response("Insufficient rights", 403)
		
		if command == 'startStream':
			self._logger.info("Start stream command received.")
			self.startStream()
			return
		if command == 'stopStream':
			self._logger.info("Stop stream command received.")
			self.stopStream()
		if command == 'checkStream':
			self._logger.info("Checking stream status.")
			if self.container:
				self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=True))
			else:
				self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=False))
				
	##~~ General Functions
	def startStream(self):
		if self._settings.global_get(["webcam","stream"]).startswith("/"):
			self._plugin_manager.send_plugin_message(self._identifier, dict(error="Webcam stream url is incorrect.  Please configure OctoPrint's Webcam & Timelapse url to include fullly qualified url, like http://192.168.0.2/webcam/?action=stream",status=True,streaming=False))
			return

		if not self.container:
			filters = []
			if self._settings.global_get(["webcam","flipH"]):
				filters.append("hflip")
			if self._settings.global_get(["webcam","flipV"]):
				filters.append("vflip")
			if self._settings.global_get(["webcam","rotate90"]):
				filters.append("transpose=cclock")
			if len(filters) == 0:
				filters.append("null")
			try:
				self.container = self.client.containers.run("octoprint/rtmpstreamer:latest",command=[self._settings.global_get(["webcam","stream"]),self._settings.get(["stream_resolution"]),self._settings.get(["stream_framerate"]),self._settings.get(["stream_url"]),",".join(filters)],detach=True,privileged=True,name="RTMPStreamer",auto_remove=True,network_mode="host")
				self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=True))
			except Exception, e:
				self._plugin_manager.send_plugin_message(self._identifier, dict(error=str(e),status=True,streaming=False))	
				
	def stopStream(self):
		if self.container:
			try:
				self.container.stop()
				self.container = None
				self._plugin_manager.send_plugin_message(self._identifier, dict(status=True,streaming=False))
			except Exception, e:
				self._plugin_manager.send_plugin_message(self._identifier, dict(error=str(e),status=True,streaming=False))
		else:
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

				# update method: pip
				pip="https://github.com/jneilliii/OctoPrint-RTMPStreamer/archive/{target_version}.zip"
			)
		)

__plugin_name__ = "RTMP Streamer"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = rtmpstreamer()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
