import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

export default defineConfig({
  site: "https://alokalok21.github.io",
  base: "/payment-routing-engine",
  trailingSlash: "ignore",
  build: { format: "directory" },
  integrations: [tailwind({ applyBaseStyles: false })],
});
