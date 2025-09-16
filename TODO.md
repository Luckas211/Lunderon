# TODO: Fix Loading Animation in Gerador and Cortes YouTube Pages

## Tasks
- [x] Move loading overlay div to avoid clipping by parent containers in gerador.html
- [x] Move loading overlay div to avoid clipping by parent containers in cortes_youtube.html
- [x] Confirm spinner animation CSS is applied correctly in video-generator.css
- [x] Create robust CSS for loading-spinner with hardcoded values and fallbacks
- [x] Enhance loading spinner with faster animation, dual borders, and glow effect
- [x] Create classic border spinner using border-top-color for clean rotation effect
- [x] Confirm FontAwesome spinner icon is used correctly in JS
- [x] Add console logs in JS to verify the "visible" class is added on form submit
- [ ] Test the loading animation on both pages after edits
- [ ] Fix any remaining issues with the animation

## Dependent Files
- core/templates/core/gerador.html
- core/templates/core/cortes_youtube.html
- core/static/core/css/video-generator.css

## Follow-up Steps
- Test the loading overlay and spinner animation on form submission
- Confirm the spinner icon spins and the overlay appears correctly
- Verify no clipping or visibility issues
