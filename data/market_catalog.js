// CommandCenter market catalog: which TradingView charts are relevant to a country or region.
// Loaded by commandcenter-map.html. Clicking a place adds its charts to the market panel (the six defaults stay).
//
// Only symbols that display in TradingView's free embedded widget are used. Many official exchange feeds
// (Nikkei, FTSE, ICE coffee futures, palm oil, rubber, iron-ore futures…) show "only available on TradingView"
// when embedded, so this list uses index CFDs, US-listed country ETFs and producer stocks as stand-ins,
// and says so in each label. Checked in the embedded widget on 2026-11-05 unless marked (unchecked).
//
// To add a place: put a line in REGIONS with a regex for the province/district name, the country code and
// the chart keys. To add a chart: put it in SYMBOLS.
window.CC_MARKET_CATALOG = (function(){
  const SYMBOLS = {
    // commodities
    COFFEE:   { tv:"PEPPERSTONE:COFFEE",     label:"Coffee (arabica)",          group:"Commodities" },
    COCOA:    { tv:"CAPITALCOM:COCOA",       label:"Cocoa",                     group:"Commodities" },
    SUGAR:    { tv:"CAPITALCOM:SUGAR",       label:"Sugar",                     group:"Commodities" },
    WHEAT:    { tv:"CAPITALCOM:WHEAT",       label:"Wheat",                     group:"Commodities" },
    CORN:     { tv:"CAPITALCOM:CORN",        label:"Corn",                      group:"Commodities" },
    SOYBEAN:  { tv:"CAPITALCOM:SOYBEAN",     label:"Soybeans",                  group:"Commodities" },
    COTTON:   { tv:"CAPITALCOM:COTTON",      label:"Cotton",                    group:"Commodities" },
    OATS:     { tv:"CAPITALCOM:OATS",        label:"Oats",                      group:"Commodities" },
    OJ:       { tv:"CAPITALCOM:ORANGEJUICE", label:"Orange juice",              group:"Commodities" },
    LUMBER:   { tv:"CAPITALCOM:LUMBER",      label:"Lumber",                    group:"Commodities" },
    CATTLE:   { tv:"PEPPERSTONE:CATTLE",     label:"Live cattle",               group:"Commodities" },
    WTI:      { tv:"TVC:USOIL",              label:"WTI crude oil",             group:"Commodities" },
    BRENT:    { tv:"TVC:UKOIL",              label:"Brent crude",               group:"Commodities" },
    NATGAS:   { tv:"CAPITALCOM:NATURALGAS",  label:"Natural gas (US)",          group:"Commodities" },
    GASOLINE: { tv:"CAPITALCOM:GASOLINE",    label:"Gasoline (US)",             group:"Commodities" },
    HEATOIL:  { tv:"CAPITALCOM:HEATINGOIL",  label:"Heating oil / diesel",      group:"Commodities" },
    GOLD:     { tv:"OANDA:XAUUSD",           label:"Gold",                      group:"Commodities" },
    SILVER:   { tv:"TVC:SILVER",             label:"Silver",                    group:"Commodities" },
    PLATINUM: { tv:"TVC:PLATINUM",           label:"Platinum",                  group:"Commodities" },
    PALLADIUM:{ tv:"TVC:PALLADIUM",          label:"Palladium",                 group:"Commodities" },
    COPPER:   { tv:"CAPITALCOM:COPPER",      label:"Copper",                    group:"Commodities" },
    // producer stocks used where no commodity price is embeddable
    TEA_KERALA:{ tv:"BSE:HARRMALAYA",  label:"Harrisons Malayalam (Kerala tea & rubber planter)", group:"Producers", note:"no tea or rubber price is embeddable; planter stock as a proxy, end-of-day" },
    TEA_ASSAM: { tv:"BSE:MCLEODRUSS",  label:"McLeod Russel (Assam tea)",        group:"Producers", note:"no tea price is embeddable; largest tea grower as a proxy, end-of-day" },
    TEA_TATA:  { tv:"BSE:TATACONSUM",  label:"Tata Consumer (Tata Tea)",         group:"Producers", note:"tea buyer and brand, end-of-day" },
    IRON_BR:   { tv:"NYSE:VALE",       label:"Vale (iron ore, Brazil)",          group:"Producers", note:"iron-ore futures aren't embeddable; largest Brazilian miner as a proxy" },
    IRON_AU:   { tv:"ASX:FMG",         label:"Fortescue (iron ore, W. Australia)", group:"Producers", note:"iron-ore futures aren't embeddable; Pilbara miner as a proxy" },
    BHP:       { tv:"NYSE:BHP",        label:"BHP (iron ore, copper, coal)",     group:"Producers" },
    // stock-market indices (CFDs that track the index) and US-listed country ETFs
    JPN225: { tv:"PEPPERSTONE:JPN225", label:"Nikkei 225 (CFD)",   group:"Indices" },
    UK100:  { tv:"PEPPERSTONE:UK100",  label:"FTSE 100 (CFD)",     group:"Indices" },
    DAX:    { tv:"XETR:DAX",           label:"DAX",                group:"Indices", note:"end-of-day" },
    FRA40:  { tv:"PEPPERSTONE:FRA40",  label:"CAC 40 (CFD)",       group:"Indices" },
    AUS200: { tv:"PEPPERSTONE:AUS200", label:"ASX 200 (CFD)",      group:"Indices" },
    HK50:   { tv:"PEPPERSTONE:HK50",   label:"Hang Seng (CFD)",    group:"Indices" },
    TSX:    { tv:"TSX:TSX",            label:"S&P/TSX Composite",  group:"Indices", note:"delayed" },
    SENSEX: { tv:"BSE:SENSEX",         label:"BSE Sensex",         group:"Indices", note:"end-of-day" },
  };
  // iShares/other US-listed country ETFs, priced in US dollars (EWZ, EWW, EWY, EZA, KSA, TUR, INDA checked; rest same exchanges, unchecked)
  const ETF = { BRA:"AMEX:EWZ", MEX:"AMEX:EWW", KOR:"AMEX:EWY", ZAF:"AMEX:EZA", SAU:"AMEX:KSA", TUR:"NASDAQ:TUR", IND:"AMEX:INDA",
    CHN:"NASDAQ:MCHI", TWN:"AMEX:EWT", IDN:"AMEX:EIDO", PHL:"AMEX:EPHE", THA:"AMEX:THD", VNM:"AMEX:VNM", MYS:"AMEX:EWM", SGP:"AMEX:EWS",
    CHL:"AMEX:ECH", PER:"AMEX:EPU", COL:"AMEX:GXG", ARG:"AMEX:ARGT", POL:"AMEX:EPOL", ISR:"AMEX:EIS", EGY:"AMEX:EGPT", NZL:"AMEX:ENZL",
    ITA:"AMEX:EWI", ESP:"AMEX:EWP", NLD:"AMEX:EWN", CHE:"AMEX:EWL", SWE:"AMEX:EWD", QAT:"NASDAQ:QAT", ARE:"NASDAQ:UAE", NGA:"AMEX:NGE",
    GRC:"AMEX:GREK", NOR:"AMEX:NORW", DNK:"AMEX:EDEN", FIN:"AMEX:EFNL", BEL:"AMEX:EWK", AUT:"AMEX:EWO", IRL:"AMEX:EIRL" };
  const ISO_NAME = { BRA:"Brazil", MEX:"Mexico", KOR:"South Korea", ZAF:"South Africa", SAU:"Saudi Arabia", TUR:"Turkey", IND:"India", CHN:"China",
    TWN:"Taiwan", IDN:"Indonesia", PHL:"Philippines", THA:"Thailand", VNM:"Vietnam", MYS:"Malaysia", SGP:"Singapore", CHL:"Chile", PER:"Peru",
    COL:"Colombia", ARG:"Argentina", POL:"Poland", ISR:"Israel", EGY:"Egypt", NZL:"New Zealand", ITA:"Italy", ESP:"Spain", NLD:"Netherlands",
    CHE:"Switzerland", SWE:"Sweden", QAT:"Qatar", ARE:"UAE", NGA:"Nigeria", GRC:"Greece", NOR:"Norway", DNK:"Denmark", FIN:"Finland",
    BEL:"Belgium", AUT:"Austria", IRL:"Ireland" };
  for (const [iso, tv] of Object.entries(ETF)) SYMBOLS["ETF_"+iso] = { tv, label:`${ISO_NAME[iso]} stocks (US-listed ETF ${tv.split(":")[1]})`, group:"Indices", note:"country ETF in US dollars, tracks the national market" };
  // the country's currency against the US dollar
  const CCY = { CAN:"CAD", MEX:"MXN", BRA:"BRL", ARG:"ARS", CHL:"CLP", COL:"COP", PER:"PEN", GBR:"GBP", CHE:"CHF", NOR:"NOK", SWE:"SEK", DNK:"DKK",
    POL:"PLN", CZE:"CZK", HUN:"HUF", ROU:"RON", TUR:"TRY", RUS:"RUB", UKR:"UAH", ISR:"ILS", SAU:"SAR", ARE:"AED", QAT:"QAR", KWT:"KWD", EGY:"EGP",
    NGA:"NGN", ZAF:"ZAR", KEN:"KES", GHA:"GHS", ETH:"ETB", MAR:"MAD", IND:"INR", PAK:"PKR", BGD:"BDT", LKA:"LKR", CHN:"CNY", HKG:"HKD", TWN:"TWD",
    KOR:"KRW", JPN:"JPY", IDN:"IDR", MYS:"MYR", THA:"THB", VNM:"VND", PHL:"PHP", SGP:"SGD", AUS:"AUD", NZL:"NZD", KAZ:"KZT", IRN:"IRR", IRQ:"IQD" };
  // euro-area countries share EUR/USD
  const EUR = ["DEU","FRA","ITA","ESP","NLD","BEL","AUT","IRL","FIN","PRT","GRC","SVK","SVN","EST","LVA","LTU","LUX","MLT","CYP","HRV"];
  // currencies quoted as XXX/USD rather than USD/XXX
  const QUOTED_FIRST = { GBP:1, AUD:1, NZD:1, EUR:1 };
  function fxKey(iso){
    const c = EUR.includes(iso) ? "EUR" : CCY[iso]; if (!c) return null;
    const pair = QUOTED_FIRST[c] ? c + "USD" : "USD" + c, key = "FX_" + pair;
    SYMBOLS[key] ||= { tv:"FX_IDC:" + pair, label: QUOTED_FIRST[c] ? `${c} / US dollar` : `US dollar / ${c}`, group:"Currencies", note:"exchange rate" };
    return key;
  }
  // country-level charts: main market + the commodities that matter most to its economy
  const COUNTRY = {
    USA:["WTI","NATGAS","CORN","SOYBEAN"], CAN:["TSX","WTI","LUMBER","GOLD"], MEX:["ETF_MEX","WTI","SILVER"], BRA:["ETF_BRA","SOYBEAN","COFFEE","IRON_BR","SUGAR"],
    ARG:["ETF_ARG","SOYBEAN","WHEAT","CORN"], CHL:["ETF_CHL","COPPER"], PER:["ETF_PER","COPPER","GOLD","SILVER"], COL:["ETF_COL","COFFEE","BRENT"],
    VEN:["BRENT"], ECU:["BRENT","COCOA"], GBR:["UK100","BRENT"], DEU:["DAX","NATGAS"], FRA:["FRA40","WHEAT"], ITA:["ETF_ITA"], ESP:["ETF_ESP"],
    NLD:["ETF_NLD","NATGAS"], CHE:["ETF_CHE","GOLD"], NOR:["ETF_NOR","BRENT","NATGAS"], SWE:["ETF_SWE"], POL:["ETF_POL","COPPER"], UKR:["WHEAT","CORN"],
    RUS:["BRENT","NATGAS","WHEAT","PALLADIUM"], TUR:["ETF_TUR","GOLD"], ISR:["ETF_ISR"], SAU:["ETF_SAU","BRENT"], ARE:["ETF_ARE","BRENT"], QAT:["ETF_QAT","NATGAS"],
    KWT:["BRENT"], IRQ:["BRENT"], IRN:["BRENT"], OMN:["BRENT"], EGY:["ETF_EGY","WHEAT","NATGAS"], NGA:["ETF_NGA","BRENT"], AGO:["BRENT"], LBY:["BRENT"], DZA:["BRENT","NATGAS"],
    ZAF:["ETF_ZAF","PLATINUM","GOLD","PALLADIUM"], GHA:["COCOA","GOLD"], CIV:["COCOA","COFFEE"], CMR:["COCOA","COFFEE"], ETH:["COFFEE"], KEN:["COFFEE","TEA_TATA"],
    UGA:["COFFEE"], TZA:["GOLD","COFFEE"], ZMB:["COPPER"], COD:["COPPER"], MLI:["GOLD","COTTON"], BFA:["GOLD","COTTON"],
    IND:["SENSEX","TEA_TATA","COTTON","SUGAR"], PAK:["COTTON","WHEAT"], BGD:["COTTON"], LKA:["TEA_TATA"], CHN:["ETF_CHN","HK50","COPPER","SOYBEAN"], HKG:["HK50"],
    TWN:["ETF_TWN"], KOR:["ETF_KOR"], JPN:["JPN225"], IDN:["ETF_IDN","COFFEE","GOLD"], MYS:["ETF_MYS"], THA:["ETF_THA","SUGAR"], VNM:["ETF_VNM","COFFEE"],
    PHL:["ETF_PHL"], SGP:["ETF_SGP"], AUS:["AUS200","IRON_AU","GOLD","BHP"], NZL:["ETF_NZL","CATTLE"], KAZ:["BRENT","COPPER"],
    GRC:["ETF_GRC"], DNK:["ETF_DNK"], FIN:["ETF_FIN","LUMBER"], BEL:["ETF_BEL"], AUT:["ETF_AUT"], IRL:["ETF_IRL"],
  };
  // regions and districts with their own signature products (matched against the clicked district, then province)
  const REGIONS = [
    { c:"IND", re:/wayanad|idukki|kodagu|coorg|chikkamagal|nilgiri/i, k:["COFFEE","TEA_KERALA","TEA_TATA"], why:"coffee and tea estates" },
    { c:"IND", re:/^kerala$/i,                         k:["TEA_KERALA","COFFEE"],        why:"tea, rubber and spice plantations" },
    { c:"IND", re:/^karn[aā]taka$/i,                   k:["COFFEE","SUGAR"],             why:"India's main coffee state" },
    { c:"IND", re:/assam|darjeeling|dibrugarh|jorhat/i, k:["TEA_ASSAM","TEA_TATA"],       why:"tea gardens" },
    { c:"IND", re:/^punjab$|haryana/i,                 k:["WHEAT","COTTON"],             why:"wheat belt" },
    { c:"IND", re:/gujar[aā]t|mah[aā]r[aā]shtra/i,     k:["COTTON","SUGAR"],             why:"cotton and sugar cane" },
    { c:"IND", re:/uttar pradesh/i,                    k:["SUGAR","WHEAT"],              why:"largest sugar-cane producer" },
    { c:"PAK", re:/punjab|sindh/i,                     k:["COTTON","WHEAT"],             why:"cotton and wheat" },
    { c:"LKA", re:/central|uva|sabaragamuwa/i,         k:["TEA_TATA"],                   why:"tea country" },
    { c:"BRA", re:/minas gerais/i,                     k:["COFFEE","IRON_BR"],           why:"coffee and iron ore" },
    { c:"BRA", re:/s[aã]o paulo/i,                     k:["SUGAR","OJ","COFFEE"],        why:"sugar cane and oranges" },
    { c:"BRA", re:/mato grosso|goi[aá]s|paran[aá]|tocantins|bahia/i, k:["SOYBEAN","CORN","COTTON"], why:"soy and grain belt" },
    { c:"BRA", re:/par[aá]$/i,                         k:["IRON_BR","CATTLE"],           why:"Carajás iron ore" },
    { c:"USA", re:/iowa|illinois|nebraska|indiana|minnesota|ohio|south dakota/i, k:["CORN","SOYBEAN"], why:"Corn Belt" },
    { c:"USA", re:/kansas|north dakota|oklahoma|montana|washington/i, k:["WHEAT"],        why:"wheat" },
    { c:"USA", re:/texas/i,                            k:["WTI","NATGAS","CATTLE","COTTON"], why:"oil, gas, cattle and cotton" },
    { c:"USA", re:/oklahoma|north dakota|new mexico|alaska/i, k:["WTI","NATGAS"],       why:"oil production" },
    { c:"USA", re:/pennsylvania|west virginia|louisiana|wyoming/i, k:["NATGAS"],        why:"natural gas" },
    { c:"USA", re:/louisiana/i,                        k:["GASOLINE","HEATOIL"],        why:"Gulf Coast refining" },
    { c:"USA", re:/florida/i,                          k:["OJ","SUGAR"],                why:"oranges and sugar cane" },
    { c:"USA", re:/nevada/i,                           k:["GOLD","SILVER"],             why:"largest US gold producer" },
    { c:"USA", re:/montana/i,                          k:["PALLADIUM","PLATINUM"],      why:"Stillwater platinum-group metals" },
    { c:"USA", re:/arizona/i,                          k:["COPPER"],                    why:"copper mining" },
    { c:"USA", re:/georgia|mississippi|alabama/i,      k:["COTTON","LUMBER"],           why:"cotton and timber" },
    { c:"USA", re:/oregon|idaho/i,                     k:["LUMBER","WHEAT"],            why:"timber and wheat" },
    { c:"CAN", re:/alberta/i,                          k:["WTI","NATGAS","CATTLE"],     why:"oil sands, gas and ranching" },
    { c:"CAN", re:/saskatchewan|manitoba/i,            k:["WHEAT","OATS"],              why:"prairie grain" },
    { c:"CAN", re:/british columbia|qu[eé]bec|new brunswick/i, k:["LUMBER"],            why:"forestry" },
    { c:"CAN", re:/ontario/i,                          k:["TSX","GOLD"],                why:"Toronto exchange and gold mines" },
    { c:"AUS", re:/western australia/i,                k:["IRON_AU","BHP","GOLD"],      why:"Pilbara iron ore and gold" },
    { c:"AUS", re:/queensland/i,                       k:["BHP","CATTLE","SUGAR"],      why:"coal, cattle and sugar cane" },
    { c:"AUS", re:/new south wales|victoria/i,         k:["WHEAT","AUS200"],            why:"grain and the Sydney exchange" },
    { c:"ARG", re:/buenos aires|c[oó]rdoba|santa fe/i, k:["SOYBEAN","WHEAT","CORN"],    why:"Pampas grain" },
    { c:"CHL", re:/antofagasta|atacama|tarapac/i,      k:["COPPER"],                    why:"copper mines" },
    { c:"COD", re:/katanga|lualaba|haut-katanga/i,     k:["COPPER"],                    why:"Copperbelt" },
    { c:"ZAF", re:/limpopo|north west|mpumalanga|gauteng/i, k:["PLATINUM","PALLADIUM","GOLD"], why:"Bushveld platinum and gold" },
    { c:"RUS", re:/krasnoyarsk|norilsk|taymyr/i,       k:["PALLADIUM","COPPER"],        why:"Norilsk metals" },
    { c:"RUS", re:/khanty|yamal|tyumen/i,              k:["BRENT","NATGAS"],            why:"West Siberian oil and gas" },
    { c:"NOR", re:/rogaland|vestland|hordaland/i,      k:["BRENT","NATGAS"],            why:"North Sea oil and gas" },
    { c:"GBR", re:/scotland/i,                         k:["BRENT"],                     why:"North Sea oil" },
    { c:"COL", re:/antioquia|caldas|huila|risaralda|quind/i, k:["COFFEE"],             why:"coffee axis" },
    { c:"VNM", re:/[ĐD][aắ]k L[aắ]k|l[aâ]m [đd][oồ]ng|gia lai/i, k:["COFFEE"],     why:"Central Highlands coffee" },
    { c:"ETH", re:/oromia|sidama|southern/i,           k:["COFFEE"],                    why:"coffee" },
    { c:"KEN", re:/kericho|nandi|bomet|nyeri|kiambu|murang/i, k:["TEA_TATA","COFFEE"], why:"tea and coffee highlands" },
    { c:"CIV", re:/.*/,                                k:["COCOA"],                     why:"world's largest cocoa grower" },
  ];
  function forPlace(iso, names){
    const keys = [], why = [];
    for (const r of REGIONS){ if (r.c !== iso) continue; if (names.some(n => n && r.re.test(n))){ keys.push(...r.k); why.push(r.why); } }
    keys.push(...(COUNTRY[iso] || []));
    const fx = fxKey(iso); if (fx) keys.push(fx);
    return { keys: [...new Set(keys)].filter(k => SYMBOLS[k]).slice(0, 7), why: [...new Set(why)] };
  }
  return { SYMBOLS, COUNTRY, REGIONS, forPlace };
})();
