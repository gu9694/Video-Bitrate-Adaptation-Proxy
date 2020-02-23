# Video-Bitrate-Adaptation-Proxy
It is a simple HTTP proxy. It accepts connections from web browsers, modifies video chunk requests as described below, opens a connection with
the web server’s IP address, and forwards the modified request to the server. Any data (the video chunks) returned by the server should be forwarded, unmodified, to the
browser.
The proxy should listen for connections from a browser on any IP address on the port specified as a command line argument (see below). It should accept
multiple concurrent connections from web browsers by starting a new thread or process for each new request. When it connects to a server, it should first bind the socket to the fake IP address specified on the command line
