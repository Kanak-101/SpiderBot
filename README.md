In development Phase

# Setting up your Laptop (Windows 11)

First connect the bot with your laptop via ethernet.

1. Open PowerShell in administrative mode and run `Get-NetAdapter` to list the connections.
2. Find the one that's your bot's Ethernet. Replace `Ethernet` with your Ethernet name in the following commands. And then run this commands:
```
Remove-NetIPAddress -InterfaceAlias "Ethernet" -Confirm:$false
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.10.2 -PrefixLength 24
Set-DNsCLientServerAddress -InterfaceAlias "Ethernet" -ResetServerAddresses
```
3. Check if the connection is successfully established by runnig this in powershell `ping 192.168.10.2`
4. Run the `laptop_server.py` python file and open `localhost:5000`

# Setting up the Raspberry Pi 4B for the Bot
The RPi should have Raspberry Pi OS Trixie

1. Clone the repo and go into RPi folder.
```
git clone "https://github.com/Kanak-101/Project_Arachnid"
cd Project_Arachnid/RPI
```
2. Run `make` and your environment will be set up.
3. To run the script `python3 rpi_node.py`
