$body = '{"username":"testplayer","password":"123456"}'
$login = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v2/game/login" -Method POST -ContentType "application/json" -Body $body
$token = $login.token
$hdr = @{"Authorization"="Bearer $token"}

Write-Host "=== battle/start (main quest 9001001, category=1) ==="
try {
    $s = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v2/game/battle/start" -Method POST -ContentType "application/json" -Headers $hdr -Body '{"quest_id":9001001,"category":1,"party_id":1,"use_boost_point":false,"use_boss_boost_point":false,"is_auto_start_mode":false,"play_id":""}'
    Write-Host "ok="$s.ok" stamina="$s.stamina
} catch { Write-Host "Error: "$_.Exception.Response.StatusCode " "$_.Exception.Response.Content }
