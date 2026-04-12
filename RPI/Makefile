.PHONY: install

install:
	@echo "--- Installing Dependencies and Script ---"
	sudo apt update && sudo apt upgrade -y
	sudo apt install -y python3-full python3-websockets python3-picamera2 python3-libcamera
	sudo apt install python3-pip -y
	pip install -r requirements.txt
	sudo nmcli connection add con-name "laptop-link" ifname eth0 type ethernet ipv4.addresses 192.168.10.1/24 ipv4.method manual ipv4.never-default yes connection.autoconnect yes
	sudo nmcli connection up "laptop-link"
	sudo chmod +x rpi_node.py
	@echo "Done. The Environment has been setup."
	python3 rpi_node.py
	@echo "Scipt is running"