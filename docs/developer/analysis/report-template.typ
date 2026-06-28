// Shared Typst template for the whz-lora study reports.
#let ink    = rgb("#1a2230")
#let muted  = rgb("#5b6876")
#let accent = rgb("#1f6feb")
#let teal   = rgb("#0e7c66")
#let good   = rgb("#1a7f37")
#let bad    = rgb("#b42318")
#let warn   = rgb("#9a6700")
#let rulec  = rgb("#d9e0e8")
#let soft   = rgb("#f5f8fb")

#let callout(body, title: none, color: accent) = block(
  width: 100%, fill: soft, stroke: (left: 3pt + color), inset: 11pt, radius: 3pt,
  spacing: 10pt,
)[#if title != none [#text(weight: "bold")[#title] \ ]#body]

// "In plain words" helper — a light teal box restating a concept for non-experts
#let plain(body) = block(fill: rgb("#edf5f0"), inset: (x: 9pt, y: 7pt), radius: 3pt, width: 100%, spacing: 9pt)[
  #text(style: "italic", size: 9pt)[#text(weight: "bold", fill: teal)[In einfachen Worten: ]#body]
]

// Table header cell helper
#let th(b) = table.cell(fill: soft)[#text(size: 8pt, weight: "bold", fill: muted)[#upper(b)]]

#let report(title: "", subtitle: "", meta: "", body) = {
  set page(
    paper: "a4", margin: (x: 2cm, top: 2cm, bottom: 1.8cm),
    footer: context [
      #line(length: 100%, stroke: 0.5pt + rulec)
      #v(1pt)
      #set text(8pt, fill: muted)
      whz-lora · Wirtschaftlichkeits- & Auslegungsstudie
      #h(1fr)
      Seite #counter(page).display() / #counter(page).final().first()
    ],
  )
  set text(font: "Segoe UI", size: 10pt, fill: ink, lang: "de")
  set par(justify: true, leading: 0.6em)
  set heading(numbering: "1.")
  show heading.where(level: 1): it => block(above: 15pt, below: 7pt)[
    #line(length: 100%, stroke: 0.5pt + rulec)
    #v(3pt)
    #text(13pt, weight: "bold", fill: ink)[#it]
  ]
  show heading.where(level: 2): it => block(above: 9pt, below: 3pt)[
    #text(11pt, weight: "bold", fill: teal)[#it]
  ]

  // Title block
  text(18pt, weight: "bold", fill: ink)[#title]
  linebreak()
  text(11pt, fill: muted)[#subtitle]
  v(3pt)
  line(length: 100%, stroke: 1.5pt + ink)
  v(2pt)
  text(8pt, fill: muted)[#meta]
  v(9pt)

  body
}
