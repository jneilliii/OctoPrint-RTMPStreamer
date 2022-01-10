$(function () {
	function rtmpstreamerViewModel(parameters) {
		var self = this;
		
		self.settingsViewModel = parameters[0];

		self.stream_resolution = ko.observable();
		self.view_url = ko.observable();
		self.stream_url = ko.observable();
		self.auto_start = ko.observable();
		self.streaming = ko.observable();
		self.processing = ko.observable(false);
		self.overlay_files = ko.observableArray([]);
		self.icon = ko.pureComputed(function() {
										var icons = [];
										if (self.streaming() && !self.processing()) {
											icons.push('icon-stop');
										} 
										
										if (!self.streaming() && !self.processing()){
											icons.push('icon-play');
										}
										
										if (self.processing()) {
											icons.push('icon-spin icon-spinner');
										} 
										
										return icons.join(' ');
									});
		self.btnclass = ko.pureComputed(function() {
										return self.streaming() ? 'btn-danger' : 'btn-primary';
									});									

		self.onBeforeBinding = function () {
			self.stream_resolution(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_resolution());
			// self.view_url(self.settingsViewModel.settings.plugins.rtmpstreamer.view_url());
			self.stream_url(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_url());
			self.auto_start(self.settingsViewModel.settings.plugins.rtmpstreamer.auto_start());
			self.overlay_files(self.settingsViewModel.settings.plugins.rtmpstreamer.overlay_files());
		};

		self.onEventSettingsUpdated = function (payload) {            
            self.stream_resolution(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_resolution());
			// self.view_url(self.settingsViewModel.settings.plugins.rtmpstreamer.view_url());
			self.stream_url(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_url());
			self.auto_start(self.settingsViewModel.settings.plugins.rtmpstreamer.auto_start());
			self.overlay_files(self.settingsViewModel.settings.plugins.rtmpstreamer.overlay_files());
        };
		
		self.onAfterBinding = function() {
			$.ajax({
					url: API_BASEURL + "plugin/rtmpstreamer",
					type: "POST",
					dataType: "json",
					data: JSON.stringify({
						command: "checkStream"
					}),
					contentType: "application/json; charset=UTF-8"
				})
		}
		
		self.onTabChange = function(next, current) {
			if(next == '#tab_plugin_rtmpstreamer'){
				if(self.settingsViewModel.settings.webcam.streamRatio() == '4:3'){
					$('#rtmpstreamer_wrapper').css('padding-bottom','75%');
				}
				self.view_url(self.settingsViewModel.settings.plugins.rtmpstreamer.view_url());
			} else {
				self.view_url('');
			}
		}
		
		self.onDataUpdaterPluginMessage = function(plugin, data) {
			if (plugin != "rtmpstreamer") {
				return;
			}
			
			if(data.error) {
				new PNotify({
							title: 'RTMP Streamer Error',
							text: data.error,
							type: 'error',
							hide: false,
							buttons: {
								closer: true,
								sticker: false
							}
							});
			}

			if(data.success) {
				new PNotify({
							title: 'RTMP Streamer',
							text: data.success,
							type: 'success',
							hide: true,
							delay: 6000,
							buttons: {
								closer: true,
								sticker: false
							}
							});
			}
			
			if(data.status) {
				if(data.streaming == true) {
					self.streaming(true);
				} else {
					self.streaming(false);
				}
				
			}
			
			self.processing(false);
        };
		
		self.toggleStream = function() {
			self.processing(true);
			if (self.streaming()) {
				$.ajax({
					url: API_BASEURL + "plugin/rtmpstreamer",
					type: "POST",
					dataType: "json",
					data: JSON.stringify({
						command: "stopStream"
					}),
					contentType: "application/json; charset=UTF-8"
				})
			} else {
				$.ajax({
					url: API_BASEURL + "plugin/rtmpstreamer",
					type: "POST",
					dataType: "json",
					data: JSON.stringify({
						command: "startStream"
					}),
					contentType: "application/json; charset=UTF-8"
				})
			}
		}
	}

	ADDITIONAL_VIEWMODELS.push([
			// This is the constructor to call for instantiating the plugin
			rtmpstreamerViewModel,
			["settingsViewModel"],
			["#settings_plugin_rtmpstreamer", "#tab_plugin_rtmpstreamer"]
		]);
});
