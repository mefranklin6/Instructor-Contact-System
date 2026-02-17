# Queries Active Directory for a JSON of EmployeeID and EmailAddress pairing

# Use this script before running the app if ID_TO_EMAIL_MODULE is set to ad_json
# This is an expensive operation and will take some time depending on your domain size

Write-Output 'Gathering AD report to pair EmployeeID to EmailAddress for all active users...'
Write-Output 'This may take some time, depending on the size of your domain'

$file_location = 'id_and_emails_from_ad.json'

try {
    Get-ADUser -Filter 'Enabled -eq $true -and EmployeeID -like "*" -and EmailAddress -like "*@*" -and EmailAddress -notlike "*-admin*"' `
        -Properties EmployeeID, EmailAddress `
        -ResultPageSize 2000 | ` # Split into multiple queries
    Select-Object @{Name = 'EmployeeID'; Expression = { $_.EmployeeID } }, `
    @{Name = 'EmailAddress'; Expression = { $_.EmailAddress } } | `
        ConvertTo-Json -Depth 3 | Out-File -FilePath $file_location -Encoding utf8

    Write-Output "Query completed. File saved to $file_location"
}
catch {
    Write-Output "Error: $_"
}
