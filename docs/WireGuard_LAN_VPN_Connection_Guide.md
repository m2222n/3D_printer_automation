# WireGuard LAN-to-VPN Network Connection Guide

## Table of Contents
1. [Current Network Structure](#1-current-network-structure)
2. [Goal](#2-goal)
3. [Solution Options](#3-solution-options)
4. [Method A: Router Routing Configuration (Recommended)](#4-method-a-router-routing-configuration-recommended)
5. [Method B: Install WireGuard Client on 6000 Server](#5-method-b-install-wireguard-client-on-6000-server)
6. [Method C: ipTIME Router WireGuard Client Mode](#6-method-c-iptime-router-wireguard-client-mode)
7. [Troubleshooting](#7-troubleshooting)
8. [References](#8-references)

---

## 1. Current Network Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Internet                                        │
└─────────────────────────────────────────────────────────────────────────────┘
           │                                           │
           │                                           │
    ┌──────┴──────┐                            ┌───────┴───────┐
    │  501 Office │                            │    Factory    │
    │   Router    │◀═══ WireGuard Tunnel ═════▶│    Router     │
    │  (ipTIME)   │         (UDP)              │               │
    └──────┬──────┘                            └───────┬───────┘
           │                                           │
    ┌──────┴──────────────┐                    ┌───────┴───────┐
    │  LAN: 192.168.100.x │                    │ LAN: 192.168. │
    │                     │                    │      219.x    │
    │  ┌───────────┐      │                    │ ┌───────────┐ │
    │  │6000 Server│      │                    │ │ Factory PC│ │
    │  │ .100.29   │      │                    │ │  .219.48  │ │
    │  │ (Linux)   │      │                    │ │ (Windows) │ │
    │  └───────────┘      │                    │ └───────────┘ │
    └─────────────────────┘                    └───────────────┘
```

### Current IP Address Summary

| Device | Local IP | VPN IP | Status |
|--------|----------|--------|--------|
| 501 Router (WireGuard Server) | 192.168.100.1 | 10.145.113.1 | ✅ Running |
| Factory PC | 192.168.219.48 | 10.145.113.3 | ✅ VPN Connected |
| 6000 Server | 192.168.100.29 | - | ❌ No VPN Access |

### Problem

The 6000 Server (192.168.100.29) cannot access the Factory PC's VPN IP (10.145.113.3).

```bash
# Running from 6000 Server - FAILS
ping 10.145.113.3              # ❌ No response
curl http://10.145.113.3:44388/  # ❌ Connection refused
```

---

## 2. Goal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Goal: Structure After Connection                          │
│                                                                             │
│   6000 Server (192.168.100.29)                                              │
│        │                                                                    │
│        ▼                                                                    │
│   501 Router (192.168.100.1 / 10.145.113.1)                                │
│        │                                                                    │
│        ▼  WireGuard Tunnel                                                 │
│   Factory PC (10.145.113.3)                                                │
│        │                                                                    │
│        ▼                                                                    │
│   PreFormServer (:44388)                                                   │
│        │                                                                    │
│        ▼                                                                    │
│   3D Printers (Form4 x 4 units)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Goal**: Enable 6000 Server to access `http://10.145.113.3:44388/`

---

## 3. Solution Options

| Method | Description | Difficulty | Recommended |
|--------|-------------|------------|-------------|
| **A** | Add Static Route on Router | ⭐ Easy | ✅ Recommended |
| **B** | Install WireGuard Client on 6000 Server | ⭐⭐ Medium | Alternative |
| **C** | Configure ipTIME Router as WireGuard Client | ⭐⭐⭐ Hard | Advanced |

---

## 4. Method A: Router Routing Configuration (Recommended)

### Concept

Since the 501 Router is already a WireGuard Server, we just need to add **routing rules** so that LAN devices can access the VPN network.

```
6000 Server → Router (Gateway) → WireGuard Interface → Factory PC
```

### 4.1 ipTIME Router Configuration (Web Interface)

#### Step 1: Access Router Admin Page
```
Browser: http://192.168.100.1
Or: http://iptime.com (from internal network)
```

#### Step 2: Navigate to Routing Settings
```
Menu Path: Advanced Settings → Network Management → Routing Settings
```

#### Step 3: Add Static Route
| Field | Value | Description |
|-------|-------|-------------|
| Destination Network | 10.145.113.0 | VPN Network |
| Subnet Mask | 255.255.255.0 | /24 |
| Gateway | (WireGuard Interface) | Router's WireGuard IP |
| Metric | 1 | Priority |

> ⚠️ **Note**: If the ipTIME router is already running WireGuard Server, routing may already be configured internally. Please check the following steps first.

### 4.2 Check: Current Router WireGuard Settings

#### Check ipTIME WireGuard Server Settings
```
Menu Path: Advanced Settings → VPN Settings → WireGuard Server Settings
```

Items to verify:
- [x] WireGuard Server enabled
- [x] VPN Internal Communication NAT setting (enabled/disabled)
- [x] Assigned VPN IP range (e.g., 10.145.113.0/24)

#### "VPN Internal Communication NAT" Setting

| Setting | Behavior | 6000 Server Access |
|---------|----------|-------------------|
| **Enabled** | VPN traffic is NATed → LAN devices can access VPN | ✅ Possible |
| **Disabled** | VPN traffic is only routed → Additional config needed | ❌ Needs setup |

### 4.3 Add Routing on 6000 Server (If Needed)

If router configuration alone doesn't work, manually add routing on the 6000 Server.

```bash
# Temporary routing (lost on reboot)
sudo ip route add 10.145.113.0/24 via 192.168.100.1

# Verify
ip route | grep 10.145.113

# Test
ping 10.145.113.3
```

#### Permanent Routing (Ubuntu/Debian)

```bash
# Edit /etc/netplan/*.yaml file
sudo nano /etc/netplan/01-netcfg.yaml
```

```yaml
network:
  version: 2
  ethernets:
    eth0:  # or actual interface name
      addresses:
        - 192.168.100.29/24
      gateway4: 192.168.100.1
      routes:
        - to: 10.145.113.0/24
          via: 192.168.100.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

```bash
# Apply
sudo netplan apply
```

---

## 5. Method B: Install WireGuard Client on 6000 Server

Use this if router configuration is difficult, or if you only want the 6000 Server to connect to VPN.

### 5.1 Install WireGuard (Ubuntu)

```bash
# Install
sudo apt update
sudo apt install wireguard

# Verify installation
wg --version
```

### 5.2 Request Configuration File

You need to request a new Peer configuration file from Faridh.

**Request details:**
```
Device Name: 6000-Server
Purpose: 3D Printer API Server
Desired VPN IP: 10.145.113.4 (or any available IP)
```

### 5.3 Configuration File Example

File format to receive from Faridh:

```ini
# /etc/wireguard/wg0.conf

[Interface]
Address = 10.145.113.4/24
PrivateKey = <Private Key provided by Faridh>
DNS = 203.248.252.2

[Peer]
PublicKey = <WireGuard_Public_Key>
AllowedIPs = 10.145.113.0/24
Endpoint = <PUBLIC_IP>:<PORT>
PersistentKeepalive = 25
```

### 5.4 Start WireGuard

```bash
# Set config file permissions
sudo chmod 600 /etc/wireguard/wg0.conf

# Start WireGuard
sudo wg-quick up wg0

# Check status
sudo wg show

# Test connection
ping 10.145.113.3
curl http://10.145.113.3:44388/
```

### 5.5 Enable Auto-start

```bash
# Enable on boot
sudo systemctl enable wg-quick@wg0

# Check service status
sudo systemctl status wg-quick@wg0
```

---

## 6. Method C: ipTIME Router WireGuard Client Mode

This method connects the entire LAN (192.168.100.x) to the VPN. The router acts as a WireGuard client.

> ⚠️ **Warning**: The 501 Router is currently running as a WireGuard **Server**. This method requires structural changes. Please review carefully.

### 6.1 ipTIME WireGuard Client Settings

```
Menu Path: Advanced Settings → VPN Settings → WireGuard Client Settings
```

Reference: [ipTIME Official WireGuard Client Guide](https://iptime.com/iptime/?page_id=67&uid=25263&mod=document)

### 6.2 Site-to-Site VPN Considerations

To fully connect two networks:

1. **Prevent IP Range Conflicts**: Both LANs must use different ranges
   - 501 Office: 192.168.100.x ✅
   - Factory: 192.168.219.x ✅ (Different → OK)

2. **AllowedIPs Configuration**: Add the other network to AllowedIPs on both sides

3. **Firewall Rules**: Allow the traffic on both sides

---

## 7. Troubleshooting

### 7.1 Connection Test Sequence

```bash
# Step 1: Verify router connection
ping 192.168.100.1

# Step 2: Verify VPN interface (from router)
ping 10.145.113.1

# Step 3: Verify Factory PC VPN IP
ping 10.145.113.3

# Step 4: Verify PreFormServer port
curl http://10.145.113.3:44388/
```

### 7.2 Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| ping 10.145.113.3 fails | No routing | Add route on router or server |
| ping works, curl fails | Firewall | Allow port 44388 in Windows Firewall on Factory PC |
| Intermittent disconnection | NAT timeout | Set PersistentKeepalive = 25 |
| Slow speed | MTU issue | Set MTU to 1420 |

### 7.3 Windows Firewall Configuration (Factory PC)

Configure Factory PC to allow port 44388 from VPN network:

```powershell
# PowerShell (Administrator)
New-NetFirewallRule -DisplayName "PreFormServer VPN" -Direction Inbound -Protocol TCP -LocalPort 44388 -RemoteAddress 10.145.113.0/24 -Action Allow
```

Or via Windows Firewall GUI:
1. Windows Defender Firewall → Advanced Settings
2. Inbound Rules → New Rule
3. Port → TCP 44388
4. Allow the connection
5. Select all profiles
6. Name: "PreFormServer VPN"

### 7.4 Check Routing Tables

```bash
# Linux (6000 Server)
ip route
traceroute 10.145.113.3

# Windows (Factory PC)
route print
tracert 10.145.113.1
```

---

## 8. References

### Official Documentation
- [WireGuard Official Site](https://www.wireguard.com/)
- [ipTIME WireGuard Server Setup (Windows)](https://iptime.com/iptime/?page_id=67&uid=25261&mod=document)
- [ipTIME WireGuard Client Setup](https://iptime.com/iptime/?page_id=67&uid=25263&mod=document)
- [ipTIME WireGuard Mobile Setup](https://iptime.com/iptime/?page_id=67&uid=25209&mod=document)

### Technical Guides
- [Ubuntu WireGuard Site-to-Site VPN](https://ubuntu.com/server/docs/wireguard-vpn-site-to-site)
- [WireGuard Site-to-Site Configuration (Pro Custodibus)](https://www.procustodibus.com/blog/2020/12/wireguard-site-to-site-config/)
- [pfSense WireGuard Site-to-Site](https://docs.netgate.com/pfsense/en/latest/recipes/wireguard-s2s.html)
- [LAN-to-LAN VPN using WireGuard](https://cosmicpercolator.com/2020/04/06/lan-to-lan-vpn-using-wireguard/)
- [Access Local Network with WireGuard](https://emersonveenstra.net/blog/access-local-network-with-wireguard/)

---

## Summary: Information for Faridh

### Recommended Method: Method A (Router Configuration)

1. **Check**: Is "VPN Internal Communication NAT" enabled in ipTIME router?
2. **If not enabled**: Enable it to allow LAN devices to access VPN
3. **If still not working**: Add manual routing on 6000 Server
   ```bash
   sudo ip route add 10.145.113.0/24 via 192.168.100.1
   ```

### Alternative: Method B (Install WireGuard on 6000 Server)

Instead of creating a new VM, installing WireGuard client on the existing 6000 Server might be faster.

Required: WireGuard Peer configuration file for 6000 Server (10.145.113.4)

---

**Document Created**: 2026-02-05
**Author**: Taemin Jeong
**Project**: 3D Printer-Robot Integration Automation System
