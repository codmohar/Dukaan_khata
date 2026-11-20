# Auto-reconnecting SSH HTTPS tunnel for DukaanAI
$ErrorActionPreference = "Continue"
Write-Host "Starting persistent tunnel watcher for port 4000..."

while ($true) {
    try {
        Write-Host "Establishing secure tunnel to localhost.run..."
        ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=10 -R 80:127.0.0.1:4000 nokey@localhost.run
    } catch {
        Write-Host "Tunnel error: $_"
    }
    Write-Host "Tunnel dropped. Reconnecting in 3 seconds..."
    Start-Sleep -Seconds 3
}

