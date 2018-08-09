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
									

		// This will get called before the rtmpstreamerViewModel gets bound to the DOM, but after its depedencies have
		// already been initialized. It is especially guaranteed that this method gets called _after_ the settings
		// have been retrieved from the OctoPrint backend and thus the SettingsViewModel been properly populated.
		self.onBefireBinding = function () {
			self.stream_resolution(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_resolution());
			// self.view_url(self.settingsViewModel.settings.plugins.rtmpstreamer.view_url());
			self.stream_url(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_url());
			self.auto_start(self.settingsViewModel.settings.plugins.rtmpstreamer.auto_start());
		};

		self.onEventSettingsUpdated = function (payload) {            
            self.stream_resolution(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_resolution());
			// self.view_url(self.settingsViewModel.settings.plugins.rtmpstreamer.view_url());
			self.stream_url(self.settingsViewModel.settings.plugins.rtmpstreamer.stream_url());
			self.auto_start(self.settingsViewModel.settings.plugins.rtmpstreamer.auto_start());
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

	// This is how our plugin registers itself with the application, by adding some configuration information to
	// the global variable ADDITIONAL_VIEWMODELS
	ADDITIONAL_VIEWMODELS.push([
			// This is the constructor to call for instantiating the plugin
			rtmpstreamerViewModel,

			// This is a list of dependencies to inject into the plugin, the order which you request here is the order
			// in which the dependencies will be injected into your view model upon instantiation via the parameters
			// argument
			["settingsViewModel"],

			// Finally, this is the list of all elements we want this view model to be bound to.
			[("#tab_plugin_rtmpstreamer")]
		]);
});
