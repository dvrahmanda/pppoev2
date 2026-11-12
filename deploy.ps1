$Host.UI.RawUI.WindowTitle = "Deploying Django Project"

# Configuration
$remoteHost = "172.16.100.26"
$remotePort = "22"
$remoteUser = "siswa"
$remotePassword = "123"
$localPath = "."
$remotePath = "/home/siswa/Project"

# Convert password to secure string
$securePassword = ConvertTo-SecureString $remotePassword -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($remoteUser, $securePassword)

Write-Host "Deploying project to $remoteHost..."

try {
    # Use scp with password authentication
    # Note: This requires scp to be available (comes with Git for Windows or OpenSSH)
    $env:SSHPASS = $remotePassword
    
    # Alternative 1: Using scp directly (if sshpass is available)
    # sshpass -e scp -P $remotePort -r $localPath/* $remoteUser@${remoteHost}:$remotePath
    
    # Alternative 2: Using PowerShell SSH module (requires PowerShell 7+ and OpenSSH)
    # You can install with: Install-Module -Name Posh-SSH -Force
    
    # Alternative 3: Manual scp call (will prompt for password)
    & scp -P $remotePort -r "$localPath/*" "$remoteUser@${remoteHost}:$remotePath"
    
} catch {
    Write-Error "Deployment failed: $_"
    exit 1
}

Write-Host "Deployment complete!"