@echo off

chcp 65001 >nul

set "PYTHONIOENCODING=utf-8"



setlocal EnableDelayedExpansion







set "JIRA_DIR=%~dp0"



for %%I in ("%JIRA_DIR%..") do set "PROJECT_DIR=%%~fI"



set "REPORT_DIR=%PROJECT_DIR%\audit_reports"







if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"







for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"







set "TRACE=%REPORT_DIR%\pipeline_trace_latest.txt"



set "TRACE_STAMPED=%REPORT_DIR%\pipeline_trace_%STAMP%.txt"







set "GIL_PROJECT_DIR=%PROJECT_DIR%"







echo ============================================================ > "%TRACE%"



echo TRACE UNIQUE IMPORT JIRA - DASHBOARD GIL >> "%TRACE%"



echo ============================================================ >> "%TRACE%"



echo Date     : %DATE% %TIME% >> "%TRACE%"



echo Projet   : %PROJECT_DIR% >> "%TRACE%"



echo Commande : %JIRA_DIR%Importer_JIRA.cmd >> "%TRACE%"



echo. >> "%TRACE%"







type "%TRACE%"







powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Continue'; & cmd.exe /d /s /c 'call ""%JIRA_DIR%Importer_JIRA.cmd""' 2>&1 | Tee-Object -FilePath '%TRACE%' -Append; exit $LASTEXITCODE"







set "RC=%ERRORLEVEL%"







echo. >> "%TRACE%"



echo ============================================================ >> "%TRACE%"



echo DIAGNOSTIC FINAL TRACE >> "%TRACE%"



echo ============================================================ >> "%TRACE%"



echo Code retour Importer_JIRA.cmd : %RC% >> "%TRACE%"



echo. >> "%TRACE%"







echo FICHIERS SUIVIS - PRESENT NE VEUT PAS DIRE PRODUIT PAR CE RUN >> "%TRACE%"



echo ------------------------------------------------------------ >> "%TRACE%"







for %%F in (



"jira\jira_brut.json"



"jira\jira_diagnostic.json"



"jira\sprints_dashboard.json"



"jira\dashboard_gil_data.json"



"jira\presentation\comparaison_sprints.json"



"jira\presentation\payload_dashboard_final.json"



"jira\sprints\sprint_courant.json"



"jira\sprints\sprint_precedent.json"



"commun\dashboard_gil.html"



"commun\dashboard_gil_sprint21.html"



"commun\dashboard_gil_data.json"



) do (



    if exist "%PROJECT_DIR%\%%~F" (



        echo OK     %%~F >> "%TRACE%"



    ) else (



        echo ABSENT %%~F >> "%TRACE%"



    )



)







echo. >> "%TRACE%"



echo RESUME PAYLOAD FINAL >> "%TRACE%"

echo ------------------------------------------------------------ >> "%TRACE%"



python -c "import os,json,pathlib; root=pathlib.Path(os.environ['GIL_PROJECT_DIR']); p=root/'jira'/'presentation'/'payload_dashboard_final.json'; d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}; print('sprintCourant =', d.get('sprintCourant')); print('sprintPrecedent =', d.get('sprintPrecedent')); print('semaineCourante =', d.get('semaineCourante')); print('santeFluxArrimage =', d.get('santeFluxArrimage')); print('kpis =', d.get('kpis')); rows=d.get('comparaisonSprints') or []; print('comparaisonSprints =', len(rows)); [print('comparaison[{}] sprint={} total={} livres={} enCours={} bloques={}'.format(i, r.get('sprint'), r.get('fluxTotal') or r.get('total'), r.get('fluxLivresTotal') or r.get('livres'), r.get('fluxEnCoursTotal') or r.get('enCours'), r.get('fluxBloquesTotal') or r.get('bloques'))) for i,r in enumerate(rows)]" >> "%TRACE%" 2>&1



echo ORDRE PIPELINE DANS Importer_JIRA.cmd >> "%TRACE%"



echo ------------------------------------------------------------ >> "%TRACE%"







findstr /n /i "publier_jira_dashboard construire_comparaison_dashboard construire_payload_dashboard_final injecter_payload_final_html preparer_dashboard_runtime dashboard_gil.html Publication" "%JIRA_DIR%Importer_JIRA.cmd" >> "%TRACE%" 2>&1







echo. >> "%TRACE%"



echo ============================================================ >> "%TRACE%"



echo TRACE TERMINEE - CODE RETOUR %RC% >> "%TRACE%"



echo Fichier principal : %TRACE% >> "%TRACE%"



echo Copie horodatée   : %TRACE_STAMPED% >> "%TRACE%"



echo ============================================================ >> "%TRACE%"







copy /Y "%TRACE%" "%TRACE_STAMPED%" >nul







echo.



echo ============================================================



echo TRACE TERMINEE



echo ============================================================



echo Fichier à transmettre :



echo %TRACE%



echo.



echo Code retour : %RC%



echo ============================================================







exit /b %RC%



