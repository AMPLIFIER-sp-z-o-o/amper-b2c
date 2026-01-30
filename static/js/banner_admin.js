/**
 * Banner Admin - Dynamic Banner Type Handling
 * 
 * This script handles the dynamic form reloading when the banner type is changed
 * during banner creation. When editing an existing banner, the banner_type field
 * is readonly, so this script only affects new banner creation.
 */
(function() {
    'use strict';
    
    document.addEventListener('DOMContentLoaded', function() {
        const bannerTypeField = document.querySelector('[name="banner_type"]');
        
        if (!bannerTypeField || bannerTypeField.hasAttribute('readonly')) {
            return;
        }
        
        // Check if we're in add mode (no existing object ID)
        const isAddMode = !window.location.pathname.includes('/change/');
        
        if (!isAddMode) {
            return;
        }
        
        bannerTypeField.addEventListener('change', function() {
            const newType = this.value;
            const currentUrl = new URL(window.location.href);
            currentUrl.searchParams.set('banner_type', newType);
            window.location.href = currentUrl.toString();
        });
    });
})();
