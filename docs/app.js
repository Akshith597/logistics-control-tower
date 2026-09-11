const views = {
  executive: {
    src: "assets/executive-overview.png",
    alt: "Power BI executive overview dashboard",
    caption: "Executive Overview — network service, revenue, margin, and exception signals in one decision surface."
  },
  carrier: {
    src: "assets/carrier-lane-performance.png",
    alt: "Power BI carrier and lane performance dashboard",
    caption: "Carrier & Lane Performance — volume-guarded rankings that connect service rates with failure counts."
  },
  model: {
    src: "assets/model-view.png",
    alt: "Power BI shipment-grain star schema model",
    caption: "Data Model — a shipment-grain fact joined to six conformed dimensions with single-direction relationships."
  }
};

const image = document.querySelector("#dashboardImage");
const caption = document.querySelector("#dashboardCaption");
document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    const view = views[button.dataset.view];
    image.src = view.src;
    image.alt = view.alt;
    caption.textContent = view.caption;
    document.querySelectorAll("[data-view]").forEach((item) => {
      item.setAttribute("aria-selected", String(item === button));
    });
  });
});
