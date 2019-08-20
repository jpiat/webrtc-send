import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import os
import sys
import logging
import http

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

#PIPELINE_DESC = '''
#webrtcbin name=send bundle-policy=max-bundle
# v4l2src device=/dev/video1 ! video/x-raw,format=YUY2,width=640,height=480,framerate=15/1 ! videoconvert ! queue ! x264enc pass=5 quantizer=21 ! rtph264pay !
# queue ! application/x-rtp,media=video,encoding-name=H264,payload=97 ! send.
#'''

PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle
 videotestsrc is-live=true pattern=ball ! videoconvert ! queue ! vp8enc deadline=1 ! rtpvp8pay !
 queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! sendrecv.
'''

KEEPALIVE_TIMEOUT = 30

async def recv_msg_ping(ws, raddr):
    '''
    Wait for a message forever, and send a regular ping to prevent bad routers
    from closing the connection.
    '''
    msg = None
    while msg is None:
        try:
            msg = await asyncio.wait_for(ws.recv(), KEEPALIVE_TIMEOUT)
        except TimeoutError:
            print('Sending keepalive ping to {!r} in recv'.format(raddr))
            await ws.ping()
    return msg



class WebRTCStreamer:

    def __init__(self, signaling_port, signaling_address, cert_path):
        self.conn = None
        self.pipe = None
        self.webrtc = None
        self.sdp_offer = None
        self.sig_port = signaling_port
        self.sig_addr = signaling_address
        self.certpath = cert_path
        self.ice_message = []

    def on_offer_created(self, promise, _, __):
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        text = offer.sdp.as_text()
        print ('Creating offer:\n%s' % text)
        msg = json.dumps({'sdp': {'type': 'offer', 'sdp': text}})
        self.sdp_offer = msg

    def on_negotiation_needed(self, element):
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        icemsg = json.dumps({'ice': {'candidate': candidate, 'sdpMLineIndex': mlineindex}})
        print ('Creating ICE:\n%s' % icemsg)
        self.ice_message.append(icemsg)

    def start_pipeline(self):
        self.pipe = Gst.parse_launch(PIPELINE_DESC)
        self.webrtc = self.pipe.get_by_name('sendrecv')
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.send_ice_candidate_message)
        self.pipe.set_state(Gst.State.PLAYING)
        print("Pipeline started")

    async def connection_handler(self, ws):
        session_opened = False
        print("Connection attempt")
        #We shoudld handle incoming messages and send the SDP as soon as a session is opened
        while True:
            msg = await recv_msg_ping(ws, ws.remote_address)
            print("{!r} command {!r}".format(ws.remote_address, msg))
            if not session_opened :
                if msg.startswith('HELLO'):
                    await ws.send('HELLO')
                #if msg.startswith('SESSION'):
                    if self.sdp_offer and self.ice_message :
                        #await ws.send('SESSION_OK')
                        await asyncio.sleep(1)
                        await ws.send(self.sdp_offer) #Sending offer now that session is connected
                        for ice_candidate in self.ice_message :
                            await ws.send(ice_candidate)
                        session_opened = True
                    else:
                        await ws.send('ERROR session is not ready yet')

    async def handler(self, ws, path):
        '''
        All incoming messages are handled here. @path is unused.
        '''
        try:
            print("Waiting for a connection")
            await self.connection_handler(ws)
        except websockets.ConnectionClosed:
            print("Connection to peer {!r} closed, exiting handler")

    async def health_check(self, path, request_headers):
        return http.HTTPStatus.OK, [], b"OK\n"

    def loop(self):
        self.start_pipeline()
        self.wsd = websockets.serve(self.handler, self.sig_addr, self.sig_port)
        print("Listening on https://{}:{}".format(self.sig_addr, self.sig_port))
        asyncio.get_event_loop().run_until_complete(self.wsd)
        asyncio.get_event_loop().run_forever()


def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True


if __name__=='__main__':
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--addr', default='127.0.0.1', help='Address to listen on (default: all interfaces, both ipv4 and ipv6)')
    parser.add_argument('--port', default=8443, type=int, help='Port to listen on')
    parser.add_argument('--keepalive-timeout', dest='keepalive_timeout', default=30, type=int, help='Timeout for keepalive (in seconds)')
    parser.add_argument('--cert-path', default=os.path.dirname(__file__))
    parser.add_argument('--disable-ssl', default=False, help='Disable ssl', action='store_true')
    options = parser.parse_args(sys.argv[1:])

    c = WebRTCStreamer(options.port, options.addr, options.cert_path)
    c.loop()

