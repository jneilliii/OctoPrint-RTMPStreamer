$(function () {
	function rtmpstreamerViewModel(parameters) {
		var self = this;
		
		self.settingsViewModel = parameters[0];

		self.dynamic_layout = ko.observableArray();
		self.selected_layout = ko.observable();
		self.imageFileName = ko.observable(undefined);
		self.imageFileURL = ko.observable(undefined);
		self.selectFilePath = undefined;

		// Returns a list of file types to accept for upload
		self.filterFileTypes = ko.computed(function() {
			return '.png,.jpg,.jpeg';
		});

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

		self.onStartup = function() {
			self.selectFilePath = $("#settings_plugin_rtmpstreamer_selectFilePath");

			self.selectFilePath.fileupload({
				dataType: "binary",
				maxNumberOfFiles: 1,
				autoUpload: false,
				add: function(e, data) {
					if (data.files.length === 0) {
						return false;
					}

					console.log(data);
					self.imageFileName(data.files[0].name);
				}
			});
		};

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
		};

		self.uploadImage = function() {
			$('#imageUploader').modal('show');
		};

		self.startUploadFromFile = function() {
			if (!self.imageFileName()) {
				alert = gettext("Image file is not specified");
				return;
			}

			$('#imageUploader').modal('hide');
			console.log(self.imageFileName());
		};

		self.startUploadFromURL = function() {
			if (!self.imageFileURL()) {
				alert = gettext("Image URL is not specified");
				return;
			}

			$('#imageUploader').modal('hide');
			console.log(self.imageFileURL());
		};

		self.rmImage = function(file) {
			showConfirmationDialog({
				message: "This is not reversible. Delete '" + file + "'?",
				onproceed: function () {
					self.doRmImage(file);
				}
			}); 
		};

		self.doRmImage = function(file) {
			$.ajax({
				url: API_BASEURL + "plugin/rtmpstreamer",
				type: "GET",
				dataType: "json",
				data: {removeImage:file},
				contentType: "application/json; charset=UTF-8"
			}).done(function(data){
				console.log(data);
				self.overlay_files(data);
			});
                };

		self.addInfo = function(data) {
			self.selected_layout({
				position: ko.observableArray([0, 0]),
				text: ko.observable(''),
				font: ko.observable(''),
				size: ko.observable(24),
				color: ko.observable('#000000')
			});
			self.settingsViewModel.settings.plugins.rtmpstreamer.dynamic_layout.push(self.selected_layout());
			self.dynamic_layout(self.settingsViewModel.settings.plugins.rtmpstreamer.dynamic_layout());
			$('#DynamicInfoEditor').modal('show');
		}

		self.editInfo = function(data) {
			console.log(data);
			self.selected_layout(data);
			$('#DynamicInfoEditor').modal('show');
		};

		self.removeInfo = function(data) {
			console.log(data);
			self.settingsViewModel.settings.plugins.rtmpstreamer.dynamic_layout.remove(data);
			self.dynamic_layout(self.settingsViewModel.settings.plugins.rtmpstreamer.dynamic_layout());
		};

	}

	ADDITIONAL_VIEWMODELS.push([
			// This is the constructor to call for instantiating the plugin
			rtmpstreamerViewModel,
			["settingsViewModel"],
			["#settings_plugin_rtmpstreamer", "#tab_plugin_rtmpstreamer"]
		]);
});
