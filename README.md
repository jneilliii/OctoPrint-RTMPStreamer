# OctoPrint-RTMPStreamer
**Overview:** Plugin that adds a tab to OctoPrint for viewing, starting, and stopping a re-encoded stream to any RTMP server.

**Details:** Based on the work found [here](https://blog.alexellis.io/live-stream-with-docker/).

**Notes:** 
- Plugin requires that OctoPrint's webcam stream uses a full url path including the ip address, ie `http://192.168.1.2/webcam/?action=stream`
- Only tested streaming to Twitch from a Pi3.
- Plugin does not provide a streaming application, it just re-encodes the mjpg stream (included with ocotpi) to a flv stream and transmits to configured RTMP server url.
- Although resolution is configurable in the plugin, the mjpg input stream being re-encoded may have a lower resolution and therefore not really be as high as you set it in the plugin settings.

<img src="https://raw.githubusercontent.com/jneilliii/Octoprint-RTMPStreamer/master/tab_screenshot.jpg">

## Prerequisites for Streaming
Follow the instructions found [here](docker_instructions.md) to install and configure docker/ffmpeg for use with this plugin for Live streaming. This is not necessary if you just want to view a url in an iframe on a tab.

## Setup
Once the prerequisites are met and the test command is successfull enter the resolution, stream url, and view url in the RTMP Streamer settings.

<img src="https://raw.githubusercontent.com/jneilliii/Octoprint-RTMPStreamer/master/settings_screenshot.jpg">

## TODO:
* [ ] Additional testing.

## Support My Efforts
I programmed this plugin for fun and do my best effort to support those that have issues with it, please return the favor and support me.

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://paypal.me/jneilliii)
