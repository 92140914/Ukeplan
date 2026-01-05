import fs from "fs";
import fetch from "node-fetch";
import cheerio from "cheerio";

const URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner";
const KLASSE = "8A";

function getWeekNumber(date = new Date()) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

const currentWeek = getWeekNumber();

const res = await fetch(URL);
const html = await res.text();
const $ = cheerio.load(html);

const tilgjengeligeUker = new Set();

$("section").each((_, el) => {
  const text = $(el).text();
  const match = text.match(/Uke\s+(\d{1,2})/i);
  if (match) tilgjengeligeUker.add(Number(match[1]));
});

if (tilgjengeligeUker.size === 0) {
  console.error("Fant ingen uker på siden");
  process.exit(1);
}

const ukeListe = [...tilgjengeligeUker].sort((a, b) => a - b);
const valgtUke = ukeListe.includes(currentWeek)
  ? currentWeek
  : ukeListe[ukeListe.length - 1];

let planHTML = "";
let ringetider = [];

$("section").each((_, el) => {
  const text = $(el).text();
  if (text.includes(`Uke ${valgtUke}`) && text.includes(KLASSE)) {
    planHTML = $(el).html();

    $(el)
      .find("time")
      .each((_, t) => {
        const tid = $(t).text().trim();
        if (/^\d{2}:\d{2}$/.test(tid)) ringetider.push(tid);
      });
  }
});

if (!planHTML) {
  console.error(`Fant ikke uke ${valgtUke} for klasse ${KLASSE}`);
  process.exit(1);
}

const data = {
  uke: valgtUke,
  klasse: KLASSE,
  html: planHTML,
  tider: ringetider,
  sistOppdatert: new Date().toISOString()
};

fs.writeFileSync("ukeplan.json", JSON.stringify(data, null, 2));
console.log(`Ukeplan lagret for uke ${valgtUke}`);

