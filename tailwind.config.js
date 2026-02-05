module.exports = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        gray: {
          400: "#737373", // default 400 is #a3a3a3
          500: "#525252", // default 500 is #737373
        },
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
      },
    },
    fontFamily: {
      body: ["Montserrat", "sans-serif"],
      sans: ["Montserrat", "sans-serif"],
    },
  },
  plugins: [require("flowbite-typography")],
};
