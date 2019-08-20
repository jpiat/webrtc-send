var html5VideoElement; 
var websocketConnection; 
var webrtcPeerConnection; 
var webrtcConfiguration; 
var reportError; 


function onLocalDescription(desc) { 
    console.log("Local description: " + JSON.stringify(desc)); 
    webrtcPeerConnection.setLocalDescription(desc).then(function() { 
        websocketConnection.send(JSON.stringify({ type: "sdp", "data": webrtcPeerConnection.localDescription })); 
    }).catch(reportError); 
} 


function onIncomingSDP(sdp) { 
    console.log("Incoming SDP: " + JSON.stringify(sdp)); 
    webrtcPeerConnection.setRemoteDescription(sdp).catch(reportError); 
    webrtcPeerConnection.createAnswer().then(onLocalDescription).catch(reportError); 
} 


function onIncomingICE(ice) { 
    var candidate = new RTCIceCandidate(ice); 
    console.log("Incoming ICE: " + JSON.stringify(ice)); 
    webrtcPeerConnection.addIceCandidate(candidate).catch(reportError); 
} 


function onAddRemoteStream(event) { 
    html5VideoElement.srcObject = event.streams[0]; 
} 


function onIceCandidate(event) { 
    if (event.candidate == null) 
    return; 

    console.log("Sending ICE candidate out: " + JSON.stringify(event.candidate)); 
    websocketConnection.send(JSON.stringify({ "type": "ice", "data": event.candidate })); 
} 


function onServerMessage(event) { 
    var msg; 

    try { 
        msg = JSON.parse(event.data); 
    } catch (e) { 
        return; 
    } 

    if (!webrtcPeerConnection) { 
        webrtcPeerConnection = new RTCPeerConnection(webrtcConfiguration); 
        webrtcPeerConnection.ontrack = onAddRemoteStream; 
        webrtcPeerConnection.onicecandidate = onIceCandidate; 
    } 
    console.log(msg);
    switch (msg.type) { 
        case "sdp": onIncomingSDP(msg.data); break; 
        case "ice": onIncomingICE(msg.data); break; 
        default: 
            console.log("Message not supported")
            break; 
    } 
} 


function playStream(videoElement, hostname, port, path, configuration, reportErrorCB) { 
var l = window.location;
var wsHost = (hostname != undefined) ? hostname : l.hostname; 
var wsPort = (port != undefined) ? port : 8443 ; 
var wsPath = (path != undefined) ? path : "ws"; 
if (wsPort) 
wsPort = ":" + wsPort; 
var wsUrl = "ws://" + wsHost + wsPort; 
console.log(wsUrl);
html5VideoElement = videoElement; 
webrtcConfiguration = configuration; 
reportError = (reportErrorCB != undefined) ? reportErrorCB : function(text) {}; 

websocketConnection = new WebSocket(wsUrl); 
websocketConnection.addEventListener("message", onServerMessage); 
} 

window.onload = function() { 
var vidstream = document.getElementById("stream"); 
var config = { 'iceServers': [{ 'urls': 'stun:stun.l.google.com:19302' }] }; 
playStream(vidstream, null, null, null, config, function (errmsg) { console.error(errmsg); }); 
}; 
