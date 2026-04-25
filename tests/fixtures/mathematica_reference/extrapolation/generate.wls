#!/usr/bin/env wolframscript
(* Generate extrapolation reference values: known series limits and the
   first N partial sums Mathematica computes at 50-digit precision.
   DataLab applies its accelerators (Richardson / Wynn-eps / Shanks /
   Levin-u) to these partial sums and the test asserts the accelerated
   value matches Mathematica's exact limit.

   Series chosen so each one has a closed-form Mathematica limit and
   well-understood convergence behaviour:

   - "zeta_2_partial_sums"      Sum_{n=1..N} 1/n^2          → Pi^2/6
   - "zeta_3_partial_sums"      Sum_{n=1..N} 1/n^3          → Zeta[3]
   - "leibniz_pi_4_partial"     Sum_{n=0..N-1} (-1)^n/(2n+1) → Pi/4
   - "alt_harmonic_log2"        Sum_{n=1..N} (-1)^(n+1)/n   → Log[2]
   - "geometric_2"              Sum_{n=0..N-1} (1/2)^n      → 2

   For the power-law extrapolation we generate triples
   E_n = E_inf + A * x_n^(-p) for known (E_inf, A, p, x1, x2, x3).
*)

(* ------------------------------------------------------------------ *)
(* Helpers (copied from special_functions/generate.wls)                *)
(* ------------------------------------------------------------------ *)
(* Format a number at 50-digit precision as a bare decimal string.
   Critical: ``RealDigits[Abs[n], 10, 50]`` returns ``{digits, expPos}``
   when ``n`` is a real numeric value, but on a symbolic exact input
   like ``Abs[3/2]`` (which Mathematica leaves un-evaluated until
   numericalised) it can return malformed shapes. ``N[x, 50]`` first
   forces a numeric value before RealDigits sees it. *)
DigitString[x_] := Module[{n, rd, digits, expPos, signStr, mantStr, lenDigits},
  n = N[x, 50];
  If[n == 0, Return["0"]];
  signStr = If[n < 0, "-", ""];
  rd = RealDigits[Abs[n], 10, 50];
  (* Defensive: bail with a recognisable error string if RealDigits
     produced anything other than a {digits, exponent} pair. *)
  If[!ListQ[rd] || Length[rd] != 2 || !ListQ[First[rd]],
    Return["RealDigits-failed-for-" <> ToString[InputForm[x]]]
  ];
  {digits, expPos} = rd;
  lenDigits = Length[digits];
  mantStr = StringJoin[ToString /@ digits];
  Which[
    expPos <= 0,
      signStr <> "0." <> StringJoin[Table["0", {-expPos}]] <> mantStr,
    expPos >= lenDigits,
      signStr <> mantStr <> StringJoin[Table["0", {expPos - lenDigits}]],
    True,
      signStr <> StringTake[mantStr, expPos] <> "." <> StringDrop[mantStr, expPos]
  ]
]

EscapeJsonString[s_] := StringJoin[
  "\"", StringReplace[s, {"\\" -> "\\\\", "\"" -> "\\\""}], "\""
]

JsonNum[x_] := EscapeJsonString[DigitString[x]]

JsonArray[xs_List] := StringJoin[
  "[", StringRiffle[Map[JsonNum, xs], ", "], "]"
]

(* ------------------------------------------------------------------ *)
(* Sequence acceleration cases                                         *)
(* Each case has:                                                      *)
(*   id, method-list, partial sums (10 terms), exact limit             *)
(* ------------------------------------------------------------------ *)

PartialSumsRange[term_, nMax_] :=
  Table[Sum[term[k], {k, 1, n}], {n, 1, nMax}]

PartialSumsFromZero[term_, nMax_] :=
  Table[Sum[term[k], {k, 0, n - 1}], {n, 1, nMax}]

(* 10 terms — enough for Wynn-eps / Levin-u to converge well below
   1e-30 for fast-converging series, and to demonstrate strong
   acceleration on slow series like Leibniz. *)
N0 = 10;

zeta2Series   = PartialSumsRange[Function[k, 1/k^2], N0];
zeta3Series   = PartialSumsRange[Function[k, 1/k^3], N0];
leibnizSeries = PartialSumsFromZero[Function[k, (-1)^k / (2 k + 1)], N0];
altHarmonic   = PartialSumsRange[Function[k, (-1)^(k + 1) / k], N0];
geometricSeries = PartialSumsFromZero[Function[k, (1/2)^k], N0];

zeta2Limit   = Pi^2 / 6;
zeta3Limit   = Zeta[3];
leibnizLimit = Pi / 4;
altLimit     = Log[2];
geometricLimit = 2;

(* Power-law cases: E_n = E_inf + A * x_n^(-p)
   The DataLab power-law extrapolator should recover E_inf exactly
   (within mpmath precision). *)
PowerLawValues[Einf_, A_, p_, xs_List] :=
  Map[Function[x, Einf + A * x^(-p)], xs]

(* Power-law cases. Each row is {id, E_inf, A, p, xs}. The numeric
   values are real Mathematica expressions (not strings) so they
   survive arithmetic and ``RealDigits`` formatting at 50-digit
   precision. *)
powerLawCases = {
  {"power_law_basic",        100,    50,   2,     {10, 20, 40}},
  {"power_law_negative_A",   1,      -3,   3/2,   {2, 4, 8}},
  {"power_law_irrational_p", 10/3,   7/2,  5/2,   {1, 2, 4}}
};

(* Emit each case as JSON *)
SequenceCase[id_, methods_, sums_, limit_, ctx_] := StringJoin[
  "    {",
  "\n      \"id\": ", EscapeJsonString[id], ",",
  "\n      \"category\": \"sequence_accelerator\",",
  "\n      \"methods\": [", StringRiffle[Map[EscapeJsonString, methods], ", "], "],",
  "\n      \"partial_sums\": ", JsonArray[sums], ",",
  "\n      \"exact_limit\": ", JsonNum[limit], ",",
  "\n      \"context\": ", EscapeJsonString[ctx],
  "\n    }"
]

PowerLawCase[id_, einf_, amp_, pVal_, xs_, energies_] := StringJoin[
  "    {",
  "\n      \"id\": ", EscapeJsonString[id], ",",
  "\n      \"category\": \"power_law\",",
  "\n      \"x_values\": ", JsonArray[N[#, 50] & /@ xs], ",",
  "\n      \"energies\": ", JsonArray[energies], ",",
  "\n      \"exact_E_inf\": ", JsonNum[einf], ",",
  "\n      \"exact_amplitude\": ", JsonNum[amp], ",",
  "\n      \"exact_exponent\": ", JsonNum[pVal],
  "\n    }"
]

(* ``methods`` field on each case lists ONLY the accelerators that
   are *expected* to converge well on this particular series at
   N=10. Tests skip non-listed methods automatically so we don't
   penalise an algorithm for a series outside its design space:
     - Richardson assumes f(h) = f_inf + c1*h^p + ...; suits
       monotone series with a polynomial-decay tail.
     - Wynn-eps / Shanks (mpmath: same algorithm) excel on
       alternating / oscillating series.
     - Levin-u: also alternating-series-friendly, with tighter
       convergence than Wynn for the same N. *)
sequenceCaseLines = {
  SequenceCase[
    "zeta_2_series",
    {"richardson"},
    zeta2Series, zeta2Limit, "monotone fast: 1/n^2 -> pi^2/6 (Richardson regime)"
  ],
  SequenceCase[
    "zeta_3_series",
    {"richardson"},
    zeta3Series, zeta3Limit, "monotone fast: 1/n^3 -> zeta(3) (Richardson regime)"
  ],
  SequenceCase[
    "leibniz_pi_4",
    {"wynn_epsilon", "shanks", "levin_u"},
    leibnizSeries, leibnizLimit, "alternating slow: Leibniz -> pi/4"
  ],
  SequenceCase[
    "alternating_harmonic",
    {"wynn_epsilon", "shanks", "levin_u"},
    altHarmonic, altLimit, "alternating: -> log(2)"
  ],
  SequenceCase[
    "geometric_half",
    {"wynn_epsilon", "shanks", "levin_u"},
    geometricSeries, geometricLimit, "geometric: -> 2"
  ]
};

powerLawCaseLines = Table[
  Module[{c, energies},
    c = powerLawCases[[i]];
    energies = PowerLawValues[c[[2]], c[[3]], c[[4]], c[[5]]];
    PowerLawCase[c[[1]], c[[2]], c[[3]], c[[4]], c[[5]], energies]
  ],
  {i, Length[powerLawCases]}
];

allCases = Join[sequenceCaseLines, powerLawCaseLines];

metadata = StringJoin[
  "  \"metadata\": {",
  "\n    \"generator\": \"tests/fixtures/mathematica_reference/extrapolation/generate.wls\",",
  "\n    \"mathematica_version\": ", EscapeJsonString[ToString[$Version]], ",",
  "\n    \"precision_digits\": 50,",
  "\n    \"description\": \"Sequence-accelerator and power-law extrapolation reference values.\"",
  "\n  }"
];

casesJson = StringJoin[
  "  \"cases\": [\n",
  StringRiffle[allCases, ",\n"],
  "\n  ]"
];

Print["{"];
Print[metadata, ","];
Print[casesJson];
Print["}"];
