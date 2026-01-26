(function () {
  "use strict";

  function toggleS3Config() {
    const providerSelect = document.getElementById("id_provider_type");
    if (!providerSelect) return;

    const s3Fieldset = document.querySelector(".s3-config");
    if (!s3Fieldset) {
      const awsField = document.getElementById("id_aws_access_key_id");
      if (awsField) {
        let parent = awsField.closest("fieldset");
        if (parent) {
          parent.classList.add("s3-config");
        }
      }
    }

    const s3Section = document.querySelector(".s3-config");
    if (!s3Section) return;

    let fieldsetElement = s3Section;
    if (!fieldsetElement.matches("fieldset")) {
      fieldsetElement = s3Section.closest("fieldset") || s3Section;
    }

    const isS3 = providerSelect.value === "s3";

    if (isS3) {
      fieldsetElement.style.display = "";
      fieldsetElement.style.opacity = "1";
    } else {
      fieldsetElement.style.display = "none";
    }
  }

  function init() {
    const providerSelect = document.getElementById("id_provider_type");
    if (!providerSelect) return;

    toggleS3Config();

    providerSelect.addEventListener("change", toggleS3Config);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
