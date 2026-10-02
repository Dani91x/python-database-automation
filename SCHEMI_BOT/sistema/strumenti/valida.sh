#!/bin/sh
# uso: valida.sh <tipo> <file.json>   (sola validazione archify, riassunto leggibile)
cd ~/.claude/skills/archify && node bin/archify.mjs validate "$1" "$2" --quality showcase --json | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const j=JSON.parse(s);console.log('ok='+j.ok, JSON.stringify(j.composition&&j.composition.summary), 'checks='+(j.checks||[]).length);for(const c of (j.checks||[]))if(!c.ok)console.log(c.name,JSON.stringify(c.details).slice(0,400));for(const d of (j.diagnostics||[]))console.log(d.severity,d.code,d.message.slice(0,260))})"
