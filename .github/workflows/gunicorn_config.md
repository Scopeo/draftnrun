# Ada Deployment with GitHub Actions & Gunicorn Zero Downtime Reload

This repository uses **GitHub Actions** to automate deployment of Ada running with **Gunicorn**. The deployment ensures **zero downtime** by using the **USR2 signal** to reload Gunicorn without stopping active requests.

---

##  Systemd Service for Gunicorn
Ensure your Gunicorn service is correctly configured with `ExecReload` to support hot reloading:

### `/etc/systemd/system/gunicorn.service`
```ini
[Unit]
Description=Gunicorn instance to serve Ada
After=network.target

[Service]
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/agentic_toolbox
ExecStart=/home/ec2-user/agentic_toolbox/.venv/bin/gunicorn -w 2 -k uvicorn.workers.UvicornWorker ada_backend.main:app --log-level debug --access-logfile /var/log/gunicorn/access.log --error-logfile /var/log/gunicorn/error.log --timeout 120
ExecReload=/bin/kill -USR2 $MAINPID
Restart=always
Type=simple

# Logging
StandardOutput=journal
StandardError=journal
StandardOutput=append:/var/log/gunicorn/stdout.log
StandardError=append:/var/log/gunicorn/stderr.log

[Install]
WantedBy=multi-user.target
```

After modifying the service file, reload systemd:
```
sudo systemctl daemon-reload
```


## Verifying Deployment

After a deployment, you can check if Gunicorn is running correctly:
```
sudo systemctl status gunicorn
```
If needed, view logs:
```
sudo journalctl -u gunicorn --since "10 minutes ago"
```

## Why Use This Setup?

✔ Zero downtime reloading using USR2
✔ Automated deployment via GitHub Actions
✔ No interrupted requests during updates
✔ Scalable and production-ready
