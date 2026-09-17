"""
Main entry point for VimCord Server.
Starts both TCP control server and UDP voice router.
"""

import argparse
import asyncio
import logging
import sys
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT
from vimcord.server.server_state import ServerState
from vimcord.server.tcp_server import TCPServer
from vimcord.server.udp_server import start_udp_server

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("VimCord.Main")


async def async_main(host: str, tcp_port: int, udp_port: int):
    server_state = ServerState()
    
    # 1. Start UDP Voice Router
    udp_transport = await start_udp_server(server_state, host, udp_port)
    logger.info(f"UDP Voice Router listening on {host}:{udp_port}")

    # 2. Start TCP Control Server
    tcp_server = TCPServer(server_state, host, tcp_port)
    logger.info(f"TCP Control Server starting on {host}:{tcp_port}")

    try:
        await tcp_server.start()
    finally:
        udp_transport.close()
        logger.info("VimCord Server shutdown complete.")


def run():
    parser = argparse.ArgumentParser(description="VimCord Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help=f"TCP port (default: {DEFAULT_TCP_PORT})")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT, help=f"UDP port (default: {DEFAULT_UDP_PORT})")
    args = parser.parse_args()

    print(f"""
==================================================
  🎙️ VimCord Server Starting...
  TCP Control Port: {args.tcp_port}
  UDP Voice Port:   {args.udp_port}
  Bind Host:        {args.host}
==================================================
    """)

    try:
        asyncio.run(async_main(args.host, args.tcp_port, args.udp_port))
    except KeyboardInterrupt:
        print("\nStopping VimCord Server...")
        sys.exit(0)


if __name__ == "__main__":
    run()
