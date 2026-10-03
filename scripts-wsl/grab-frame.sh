#!/bin/bash
out="${1:-$HOME/frame0.png}"
curl -s -o "$out" -w "HTTP %{http_code}  %{size_download} octets  %{time_total}s\n" --max-time 10 http://127.0.0.1:8080/frame
file "$out"
