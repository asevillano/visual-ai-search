$sw = [System.Diagnostics.Stopwatch]::StartNew()
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/search' -Method Post -ContentType 'application/json' -Body '{"text":"red car","top":3}'
$sw.Stop()
Write-Host "Round-trip: $($sw.ElapsedMilliseconds) ms"
Write-Host "AI Search results: $($r.ai_search_results.Count)"
Write-Host "OpenAI results: $($r.openai_search_results.Count)"
