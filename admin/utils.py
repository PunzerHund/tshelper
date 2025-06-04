import os, shutil, subprocess

def create_bot_instance(login, template_dir='/opt/mentorbot'):
    dest = os.path.join('/opt/mentors', login)
    if os.path.exists(dest):
        raise FileExistsError(f"{dest} already exists")
    shutil.copytree(template_dir, dest)
    return dest

def create_systemd_service(login):
    service_name = f"mentorbot_{login}.service"
    unit = f"""[Unit]
Description=MentorBot instance for {login}
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mentors/{login}
ExecStart=/usr/bin/python3 bot.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
"""
    path = f"/etc/systemd/system/{service_name}"
    with open(path, "w") as f:
        f.write(unit)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", service_name], check=True)
    return service_name
