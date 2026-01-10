# Node Miner

Bitcoin CPU mining on your Umbrel node - for education and fun.

## Overview

Node Miner enables Bitcoin CPU mining directly on your Umbrel node using cpuminer-multi. This app is designed for node operators who want to experiment with Bitcoin mining without dedicated mining hardware like a Bitaxe.

**This is for education and fun, not profit.**

CPU mining Bitcoin is completely unprofitable due to the network's difficulty. You will spend more on electricity than you'll ever earn. This app is meant for:
- Learning how Bitcoin mining works
- Experimenting with mining pools
- Supporting specific pools for educational purposes
- Having fun with your node

## Screenshots

![Dashboard](gallery/1.jpg)
*Mining dashboard with real-time statistics and controls*

![Pool Settings](gallery/2.jpg)
*Pool configuration interface*

## Features

- **Flexible Pool Configuration**: Connect to external mining pools or internal pools running on the same system
  - For internal pools (e.g., on the same Umbrel), use the internal IP: `172.17.0.1`
- **Adjustable CPU Usage**: Set mining intensity from 1-100% of your CPU power
- **Real-time Dashboard**: Monitor hashrate, mining statistics, and system resources
- **Simple Controls**: Easy start/stop buttons with live status updates

## Installation

1. Install Node Miner from the Umbrel Community App Store
2. Open the app from your Umbrel dashboard
3. Configure your pool settings
4. Start mining!

## Important Warnings

⚠️ **CPU Mining is Unprofitable** - You will not make money. Electricity costs will far exceed any rewards.

⚠️ **System Overload Risk** - Mining with high CPU percentages (>50%) can overload your system and make it unresponsive. **Be extremely careful** with CPU usage settings. Start low (10-20%) and monitor your system.

⚠️ **For Education Only** - This app is meant for learning and experimentation, not as a source of income.

## Configuration

### Pool URL
Enter your mining pool URL. Formats accepted:
- `stratum+tcp://pool.example.com:3333`
- `pool.example.com:3333`
- `172.17.0.1:2018` (for internal pools)

**Important**: If you're running a mining pool on the same Umbrel system, use the internal IP address `172.17.0.1` instead of localhost or 127.0.0.1.

### CPU Usage
Choose carefully! Recommended:
- **10-20%**: Safe for most systems
- **30-40%**: Monitor system responsiveness
- **50%+**: ⚠️ High risk of system overload - not recommended

## Credits & Acknowledgments

This app is built on top of excellent open-source software:

### cpuminer-multi
Mining engine by tpruvot
- GitHub: https://github.com/tpruvot/cpuminer-multi
- License: GPL-2.0

### Black Dashboard
UI theme by Creative Tim
- Website: https://www.creative-tim.com/product/black-dashboard
- License: MIT License

## License

This app uses cpuminer-multi (GPL-2.0) and Black Dashboard (MIT License).

## Support

For issues or questions:
- GitHub Issues: https://github.com/BTCDataGuy/node-miner/issues
- X (Twitter): https://x.com/BTCDataGuy
