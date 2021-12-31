**Install docker**

    curl -sSL https://get.docker.com | sh
    sudo usermod pi -aG docker
    sudo reboot

    docker pull kolisko/rpi-ffmpeg:latest
	
**OctoPrint Settings**

- Enter your stream url used above in the OctoPrint-RTMPStreamer plugin settings.
- Change your webcam stream url to a fully quliafied url using the ip address of your pi like

    `http://127.0.0.1/webcam/?action=stream`
	
