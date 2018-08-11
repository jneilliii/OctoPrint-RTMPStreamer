**Install docker**

    curl -sSL https://get.docker.com | sh
    sudo usermod pi -aG docker
    sudo reboot

**Clone Repository and Build Docker Image**

    cd ~
    git clone https://github.com/jneilliii/rtmpstreamer --depth 1
	cd rtmpstreamer
	docker build -t octoprint/rtmpstreamer .	
	
**Test**

Run the following command replacing `<ip>`, `<stream url>`, `<stream resolution>` and `<stream framerate>` with appropriate values. For the resolution setting use the format equivalent to 640x480.

    docker run --privileged --name RTMPStreamer -ti octoprint/rtmpstreamer:latest http://<ip>/webcam/?action=stream <stream resolution> <stream framerate> <stream url> null 

Stream should go live and re-encode the OctoPrint stream to provided url.  Once verified close ffmpeg and remove docker container.
	
	ctrl+c
	docker rm RTMPStreamer
	
**OctoPrint Settings**

- Enter your stream url used above in the OctoPrint-RTMPStreamer plugin settings.
- Change your webcam stream url to a fully quliafied url using the ip address of your pi like

    `http://192.168.1.101/webcam/?action=stream`
	
