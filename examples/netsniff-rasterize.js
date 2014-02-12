/**
 * Largely a combination of PhantomJs' default 'rasterize' and 'netsniff'
 * scripts. This adds the potential for including 'renderedElements', i.e.
 * images of particular elements within a page, in the output.
 *
 * This breaks the HAR spec. as it currently stands.
 */



if (!Date.prototype.toISOString) {
	Date.prototype.toISOString = function () {
		function pad(n) { return n < 10 ? '0' + n : n; }
		function ms(n) { return n < 10 ? '00'+ n : n < 100 ? '0' + n : n }
		return this.getFullYear() + '-' +
			pad(this.getMonth() + 1) + '-' +
			pad(this.getDate()) + 'T' +
			pad(this.getHours()) + ':' +
			pad(this.getMinutes()) + ':' +
			pad(this.getSeconds()) + '.' +
			ms(this.getMilliseconds()) + 'Z';
	}
}

function createHAR(address, title, startTime, resources, b64_content, b64_image )
{
	var entries = [];

	resources.forEach(function (resource) {
		var request = resource.request,
			startReply = resource.startReply,
			endReply = resource.endReply;

		if (!request || !startReply || !endReply) {
			return;
		}

		// Exclude Data URI from HAR file because
		// they aren't included in specification
		if (request.url.match(/(^data:image\/.*)/i)) {
			//Include these; we're already breaking the spec.
			//return;
		}

		entries.push({
			startedDateTime: request.time.toISOString(),
			time: endReply.time - request.time,
			request: {
				method: request.method,
				url: request.url,
				httpVersion: "HTTP/1.1",
				cookies: [],
				headers: request.headers,
				queryString: [],
				headersSize: -1,
				bodySize: -1
			}
		});
		if( request.url === address ) {
			entries.push({
				response: {
					status: endReply.status,
					statusText: endReply.statusText,
					httpVersion: "HTTP/1.1",
					cookies: [],
					headers: endReply.headers,
					redirectURL: "",
					headersSize: -1,
					bodySize: startReply.bodySize,
					content: {
						size: startReply.bodySize,
						mimeType: endReply.contentType,
						text: b64_content,
						renderedElements: [
							{
								selector: ":root",
								format: "PNG",
								content: b64_image,
								encoding: "base64"
							}
						]
					}
				}
			});
		} else {
			entries.push({
				response: {
					status: endReply.status,
					statusText: endReply.statusText,
					httpVersion: "HTTP/1.1",
					cookies: [],
					headers: endReply.headers,
					redirectURL: "",
					headersSize: -1,
					bodySize: startReply.bodySize,
					content: {
						size: startReply.bodySize,
						mimeType: endReply.contentType
					}
				}
			});
		}
		entries.push({
			cache: {},
			timings: {
				blocked: 0,
				dns: -1,
				connect: -1,
				send: 0,
				wait: startReply.time - request.time,
				receive: endReply.time - startReply.time,
				ssl: -1
			},
			pageref: address
		});
	});

	return {
		log: {
			version: '1.2',
			creator: {
				name: "PhantomJS",
				version: phantom.version.major + '.' + phantom.version.minor +
					'.' + phantom.version.patch
			},
			pages: [{
				startedDateTime: startTime.toISOString(),
				id: address,
				title: title,
				pageTimings: {
					onLoad: page.endTime - page.startTime
				}
			}],
			entries: entries
		}
	};
}

var page = require('webpage').create(),
	system = require('system');

if (system.args.length === 1) {
	console.log('Usage: netsniff-rasterize.js URL filename [paperwidth*paperheight|paperformat] [zoom]');
	console.log('  paper (pdf output) examples: "5in*7.5in", "10cm*20cm", "A4", "Letter"');
	phantom.exit(1);
} else {

	page.address = system.args[1];
	page.resources = [];

	page.onLoadStarted = function () {
		page.startTime = new Date();
	};

	page.onResourceRequested = function (req) {
		page.resources[req.id] = {
			request: req,
			startReply: null,
			endReply: null
		};
	};

	page.onResourceReceived = function (res) {
		if (res.stage === 'start') {
			page.resources[res.id].startReply = res;
		}
		if (res.stage === 'end') {
			page.resources[res.id].endReply = res;
		}
	};

	output = system.args[2];
	page.viewportSize = { width: 1280, height: 960 };
	if (system.args.length > 3 && system.args[2].substr(-4) === ".pdf") {
		size = system.args[3].split('*');
		page.paperSize = size.length === 2 ? { width: size[0], height: size[1], margin: '0px' }
										   : { format: system.args[3], orientation: 'portrait', margin: '1cm' };
	}
	if (system.args.length > 4) {
		page.zoomFactor = system.args[4];
	}

	page.open(page.address, function (status) {
		if (status !== 'success') {
			console.log('FAIL to load the address');
			phantom.exit(1);
		} else {
			page.endTime = new Date();
			page.title = page.evaluate(function () {
				return document.title;
			});
			var b64_image = page.renderBase64( "PNG" );
			var b64_content = window.btoa( unescape( encodeURIComponent( page.content ) ) );
			var har = createHAR( page.address, page.title, page.startTime, page.resources, b64_content, b64_image );
			console.log(JSON.stringify(har, undefined, 4));
			phantom.exit();
		}
	});
}

