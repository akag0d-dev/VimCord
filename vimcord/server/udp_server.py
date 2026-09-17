"""
UDP Voice Router for VimCord.
Handles high-speed, low-latency forwarding of audio frames.
"""

import asyncio
import logging
from typing import Tuple
from vimcord.common.protocol import (
    unpack_udp_audio,
    pack_udp_audio,
    UDP_TYPE_REGISTER,
    UDP_TYPE_CHANNEL_AUDIO,
    UDP_TYPE_DM_AUDIO,
    UDP_TYPE_PING,
    UDP_TYPE_SPEAKING,
    UDP_TYPE_SCREEN_FRAME
)
from vimcord.server.server_state import ServerState

logger = logging.getLogger("VimCord.UDPServer")


class VoiceServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, server_state: ServerState):
        super().__init__()
        self.server_state = server_state
        self.transport: asyncio.DatagramTransport = None

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport
        logger.info("UDP Voice Router started.")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        packet = unpack_udp_audio(data)
        if not packet:
            return
        
        pkt_type, seq, sender_id, target_id, payload = packet

        if pkt_type == UDP_TYPE_REGISTER or pkt_type == UDP_TYPE_PING:
            # Register or refresh client's UDP endpoint
            self.server_state.register_udp(sender_id, addr[0], addr[1])
            # Send ping response back so client knows UDP is working
            ack = pack_udp_audio(UDP_TYPE_PING, seq, "server", sender_id)
            self.transport.sendto(ack, addr)
            return

        elif pkt_type in (UDP_TYPE_CHANNEL_AUDIO, UDP_TYPE_SPEAKING):
            # Forward to all other participants in the same voice channel
            channel_id = target_id
            recipients = self.server_state.get_channel_voice_recipients(sender_id, channel_id)
            for r_addr in recipients:
                self.transport.sendto(data, r_addr)

        elif pkt_type == UDP_TYPE_DM_AUDIO:
            # Forward directly to the 1-on-1 call peer
            call_id = target_id
            peer_addr = self.server_state.get_call_peer_udp(sender_id, call_id)
            if peer_addr:
                self.transport.sendto(data, peer_addr)

        elif pkt_type == UDP_TYPE_SCREEN_FRAME:
            # Screen frame can be sent to a room voice channel or a direct call
            recipients = self.server_state.get_channel_voice_recipients(sender_id, target_id)
            if recipients:
                for r_addr in recipients:
                    self.transport.sendto(data, r_addr)
            else:
                peer_addr = self.server_state.get_call_peer_udp(sender_id, target_id)
                if peer_addr:
                    self.transport.sendto(data, peer_addr)

    def error_received(self, exc):
        logger.warning(f"UDP error: {exc}")


async def start_udp_server(server_state: ServerState, host: str, port: int) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: VoiceServerProtocol(server_state),
        local_addr=(host, port)
    )
    return transport
