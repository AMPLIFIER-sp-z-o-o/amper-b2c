(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const sectionTypeSelect = document.getElementById('id_section_type');
        
        if (!sectionTypeSelect) {
            return;
        }

        const isAddPage = window.location.pathname.includes('/add/');
        
        if (!isAddPage) {
            return;
        }

        const urlParams = new URLSearchParams(window.location.search);
        const currentSectionType = urlParams.get('section_type');

        if (currentSectionType && sectionTypeSelect.value !== currentSectionType) {
            sectionTypeSelect.value = currentSectionType;
        }

        let initialValue = sectionTypeSelect.value;

        sectionTypeSelect.addEventListener('change', function(e) {
            const newValue = e.target.value;
            
            if (newValue !== initialValue) {
                const url = new URL(window.location.href);
                url.searchParams.set('section_type', newValue);
                window.location.href = url.toString();
            }
        });
    });
})();
