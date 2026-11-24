@echo off
REM Construit les deux executables Windows de SecureID dans le dossier dist\
REM A lancer depuis la racine du projet.

call .venv\Scripts\activate || goto :erreur
pip install --timeout 120 --retries 10 pyinstaller || goto :erreur

pyinstaller --noconfirm --windowed --name SecureID-Emission --collect-data reportlab launch_issuer.py || goto :erreur
pyinstaller --noconfirm --windowed --name SecureID-Verification --collect-data reportlab launch_verifier.py || goto :erreur

echo.
echo Termine :
echo   dist\SecureID-Emission\SecureID-Emission.exe
echo   dist\SecureID-Verification\SecureID-Verification.exe
echo Les donnees des executables sont dans %USERPROFILE%\SecureID
goto :eof

:erreur
echo.
echo La construction a echoue : lis le message d erreur ci-dessus.
exit /b 1
