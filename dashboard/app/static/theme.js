(() => {
  let choice = "system";
  try {
    choice = localStorage.getItem("marketing-theme") || "system";
  } catch (_) {}
  const media = matchMedia("(prefers-color-scheme: dark)");
  const apply = () => {
    document.documentElement.dataset.theme =
      choice === "system" ? (media.matches ? "dark" : "light") : choice;
    document.documentElement.dataset.themeChoice = choice;
  };
  apply();
  media.addEventListener("change", apply);
  window.marketingTheme = (value) => {
    choice = value;
    try {
      localStorage.setItem("marketing-theme", value);
    } catch (_) {}
    apply();
  };
})();
