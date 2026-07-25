# Troubleshooting

## Service Not Starting
- Check `systemctl status <unit>`
- Check journal logs: `journalctl -u <unit> -n 100 --no-pager`
- Verify WorkingDirectory and ExecStart paths

## Wrong Version in UI
- Verify `/opt/carhunter/current` symlink target
- Verify `templates/base.html` version marker in target directory
- Restart web service

## Wrong Port
- Verify `webapp.py` port per environment
- Verify active listeners: `ss -ltn | grep -E ':5000|:5001'`

## Database Locked
- Check concurrent pipeline/manual runs
- Retry after lock release
- Confirm service and manual tasks are not overlapping
