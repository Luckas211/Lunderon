# TODO: Fix Django Video Generator Application

## Completed Tasks
- [x] Analyze project structure and dependencies
- [x] Create comprehensive plan
- [x] Remove Google Cloud Text-to-Speech from requirements.txt
- [x] Remove narrator-related functions from views.py
- [x] Update GeradorForm to remove narrator fields
- [x] Update VideoGerado model to remove narrator fields
- [x] Run database migrations
- [x] Fix video generation logic to handle missing base media
- [x] Populate database with categories and base media
- [x] Create test user with active subscription
- [x] Test server startup and basic functionality
- [x] Fix FFmpeg filter_complex syntax error
- [x] Test video generation end-to-end (fixed FFmpeg command)

## Pending Tasks
- [ ] Verify all templates are working correctly
- [ ] Clean up temporary files and scripts

## New Tasks: Change Site Name to LUNDERON
- [x] Change "L.E DARK" to "LUNDERON" in all HTML templates (titles, logos, footers)
- [x] Change "L.E. DARK" to "LUNDERON" in HTML templates
- [x] Change "Equipe L.E DARK" to "Equipe LUNDERON" in email template
- [x] Change "Canal Dark" to "Canal LUNDERON" in home.html
- [x] Change "canais dark" to "canais LUNDERON" in home.html
- [x] Change "canal dark" to "canal LUNDERON" in como_funciona.html
- [x] Change "vídeos para canais dark" to "vídeos para canais LUNDERON" in home.html
- [x] Change "L.E DARK" to "LUNDERON" in views.py (email subjects and messages)
- [x] Change "ledark.sac@gmail.com" to "lunderon.sac@gmail.com" in views.py and test_email.py
- [ ] Rename directory from "site-dark" to "lunderon" (Note: Cannot rename while files are open in VSCode. Please close VSCode and manually rename the directory from "site-dark" to "lunderon")
