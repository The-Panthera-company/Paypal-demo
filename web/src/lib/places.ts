// Approximate coordinates for the place names projects use as their region, for globe pins.
// Not geolocation: a project with an unknown place simply gets no pin. Add places as projects arrive.
const PLACES: Record<string, [number, number]> = {
  // Towns and cities
  nairobi: [-1.29, 36.82],
  mombasa: [-4.04, 39.67],
  kisumu: [-0.09, 34.77],
  nakuru: [-0.3, 36.07],
  eldoret: [0.51, 35.27],
  turkana: [3.12, 35.6],
  kampala: [0.35, 32.58],
  "dar es salaam": [-6.79, 39.21],
  kigali: [-1.95, 30.06],
  addis_ababa: [9.03, 38.74],
  lagos: [6.52, 3.38],
  accra: [5.6, -0.19],
  dakar: [14.72, -17.47],
  johannesburg: [-26.2, 28.05],
  cairo: [30.04, 31.24],
  mumbai: [19.08, 72.88],
  delhi: [28.61, 77.21],
  dhaka: [23.81, 90.41],
  manila: [14.6, 120.98],
  jakarta: [-6.21, 106.85],
  "mexico city": [19.43, -99.13],
  lima: [-12.05, -77.04],
  "são paulo": [-23.55, -46.63],
  london: [51.51, -0.13],
  berlin: [52.52, 13.4],
  // Regions (sample data)
  "east africa": [-1.29, 36.82],
  "west africa": [6.52, 3.38],
  "south asia": [23.81, 90.41],
  "southeast asia": [14.6, 120.98],
  "latin america": [-12.05, -77.04],
  europe: [50.85, 4.35],
};

export function placeLocation(region: string): [number, number] | null {
  const key = region.trim().toLowerCase();
  return PLACES[key] ?? PLACES[key.replace(/\s+/g, "_")] ?? null;
}
