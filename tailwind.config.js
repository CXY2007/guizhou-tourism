/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        ink: "#0E2A24",
        teal: "#1F4E5A",
        cinnabar: "#B83A2D",
        paper: "#F4EFE6",
        gold: "#C9A227",
        mist: "#8FA6A0",
      },
      fontFamily: {
        display: ['"Noto Serif SC"', '"Songti SC"', "serif"],
        body: ["Inter", '"PingFang SC"', '"Microsoft YaHei"', "system-ui", "sans-serif"],
      },
      borderRadius: {
        sm: "4px",
        md: "8px",
        lg: "16px",
        xl: "24px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(14,42,36,.08)",
        md: "0 8px 24px rgba(14,42,36,.12)",
        lg: "0 24px 64px rgba(14,42,36,.18)",
      },
      transitionTimingFunction: {
        smooth: "cubic-bezier(.22,1,.36,1)",
      },
    },
  },
  plugins: [],
};
