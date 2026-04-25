#!/usr/bin/env wolframscript
(* Generate ground-truth values for every special function in DataLab's
   whitelist (datalab_latex/expression_engine.py:_ALLOWED_FUNCTIONS).

   Each function is evaluated at 3-5 representative arguments at 50-digit
   precision. The output is JSON which the tests load and compare against
   DataLab's mpmath evaluation via expression_engine.safe_eval.

   Run:    wolframscript -file generate.wls > ground_truth.json
   Verify: python -c "import json; json.load(open('ground_truth.json'))"
*)

(* ------------------------------------------------------------------ *)
(* Helper: format an mpf-style decimal string at 50 digits.            *)
(* Mathematica's N[x, 50] yields "0.123...`50." — strip the backtick   *)
(* suffix so json.loads + mp.mpf can parse the result cleanly.         *)
(* ------------------------------------------------------------------ *)
(* Format a number at 50-digit precision as a bare decimal string.
   Approach: use ``RealDigits`` (which reliably returns the digits +
   decimal-point position regardless of input's machine-precision
   status), then assemble the string by hand so no formatter has a
   chance to truncate to IEEE 754 double. *)
DigitString[x_] := Module[{n, digits, expPos, signStr, mantStr, lenDigits},
  n = N[x, 50];
  If[n == 0,
    Return["0"]
  ];
  signStr = If[n < 0, "-", ""];
  {digits, expPos} = RealDigits[Abs[n], 10, 50];
  lenDigits = Length[digits];
  mantStr = StringJoin[ToString /@ digits];
  (* expPos is the position OF the decimal point counted from the
     left of the significand, 1-based. We render either as
     "0.000...digits" (when expPos <= 0), "d.ddddd"·10^k via a fixed
     left-aligned 0.<padding><digits>·10^expPos, or as a
     plain "ddd.ddd" form when 1 <= expPos <= lenDigits. *)
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

(* Format a Mathematica list of args as a JSON array. Each arg is
   either a number (rendered via Mathematica's InputForm) or a
   pre-quoted symbolic string ("Pi/4", "1/2") that we keep as a JSON
   string so the test side can ``mpmathify`` it back to a high-
   precision value. *)
ArgsAsJsonArray[args_List] := StringJoin[
  "[",
  StringRiffle[
    Map[
      Function[a,
        If[StringQ[a],
          EscapeJsonString[a],
          ToString[a, InputForm]
        ]
      ],
      args
    ],
    ", "
  ],
  "]"
]

CaseEntry[id_, fn_, args_, value_, ctx_] := StringJoin[
  "    {",
  "\n      \"id\": ", EscapeJsonString[id], ",",
  "\n      \"function\": ", EscapeJsonString[fn], ",",
  "\n      \"args\": ", ArgsAsJsonArray[args], ",",
  "\n      \"value\": ", EscapeJsonString[DigitString[value]], ",",
  "\n      \"context\": ", EscapeJsonString[ctx],
  "\n    }"
]

(* ------------------------------------------------------------------ *)
(* Test cases — covers every entry in DataLab's whitelist.              *)
(* Each case is a tuple {id, function-name, args, exact-value, ctx}.   *)
(* The function-name matches DataLab's Mathematica-style spelling      *)
(* (Sin, Cos, Erf, Gamma, ...) so the test can build a DataLab         *)
(* expression string directly from this entry.                          *)
(* ------------------------------------------------------------------ *)

cases = {
  (* Trigonometric *)
  {"Sin[1]",       "Sin",   {1},        Sin[1],         "trig"},
  {"Sin[Pi/4]",    "Sin",   {"Pi/4"},   Sin[Pi/4],      "trig"},
  {"Cos[1]",       "Cos",   {1},        Cos[1],         "trig"},
  {"Cos[Pi/3]",    "Cos",   {"Pi/3"},   Cos[Pi/3],      "trig"},
  {"Tan[Pi/6]",    "Tan",   {"Pi/6"},   Tan[Pi/6],      "trig"},

  (* Inverse trig *)
  {"Asin[1/2]",    "Asin",  {"1/2"},    ArcSin[1/2],    "inverse_trig"},
  {"Acos[1/2]",    "Acos",  {"1/2"},    ArcCos[1/2],    "inverse_trig"},
  {"Atan[1]",      "Atan",  {1},        ArcTan[1],      "inverse_trig"},

  (* Hyperbolic *)
  {"Sinh[1]",      "Sinh",  {1},        Sinh[1],        "hyperbolic"},
  {"Cosh[1]",      "Cosh",  {1},        Cosh[1],        "hyperbolic"},
  {"Tanh[1]",      "Tanh",  {1},        Tanh[1],        "hyperbolic"},
  {"Asinh[1]",     "Asinh", {1},        ArcSinh[1],     "hyperbolic"},
  {"Acosh[2]",     "Acosh", {2},        ArcCosh[2],     "hyperbolic"},
  {"Atanh[1/2]",   "Atanh", {"1/2"},    ArcTanh[1/2],   "hyperbolic"},

  (* Exp / log *)
  {"Exp[1]",       "Exp",   {1},        Exp[1],         "exp_log"},
  {"Exp[-1]",      "Exp",   {-1},       Exp[-1],        "exp_log"},
  {"Log[2]",       "Log",   {2},        Log[2],         "exp_log"},
  {"Log[10]",      "Log",   {10},       Log[10],        "exp_log"},
  {"Log10[1000]",  "Log10", {1000},     Log10[1000],    "exp_log"},
  {"Sqrt[2]",      "Sqrt",  {2},        Sqrt[2],        "exp_log"},
  {"Power[2,10]",  "Power", {2, 10},    Power[2, 10],   "exp_log"},

  (* Abs *)
  {"Abs[-3.5]",    "Abs",   {"-7/2"},   Abs[-7/2],      "abs"},

  (* Special — Erf, Gamma *)
  {"Erf[1]",       "Erf",   {1},        Erf[1],         "special"},
  {"Erf[2]",       "Erf",   {2},        Erf[2],         "special"},
  {"Gamma[5]",     "Gamma", {5},        Gamma[5],       "special"},
  {"Gamma[1/2]",   "Gamma", {"1/2"},    Gamma[1/2],     "special"},

  (* Riemann zeta *)
  {"Zeta[2]",      "Zeta",  {2},        Zeta[2],        "zeta"},
  {"Zeta[3]",      "Zeta",  {3},        Zeta[3],        "zeta"},
  {"Zeta[4]",      "Zeta",  {4},        Zeta[4],        "zeta"},

  (* Hypergeometric — DataLab maps these to mpmath.hyp0f1 / hyp1f1 / hyp2f1.
     Mathematica's spelling is HypergeometricPFQ / Hypergeometric0F1 etc.
     Use cases that match mpmath's call signature: hyp0f1(b, z),
     hyp1f1(a, b, z), hyp2f1(a, b, c, z). *)
  {"Hyp0f1[2,1]",      "Hyp0f1", {2, 1},               Hypergeometric0F1[2, 1],          "hypergeometric"},
  {"Hyp1f1[1,2,1]",    "Hyp1f1", {1, 2, 1},            Hypergeometric1F1[1, 2, 1],       "hypergeometric"},
  {"Hyp2f1[1/2,1,3/2,1/4]", "Hyp2f1", {"1/2", 1, "3/2", "1/4"},  Hypergeometric2F1[1/2, 1, 3/2, 1/4],  "hypergeometric"},

  (* PolyLog — Li_s(z). DataLab maps PolyLog -> mpmath.polylog. *)
  {"PolyLog[2,1/2]", "PolyLog", {2, "1/2"}, PolyLog[2, 1/2], "polylog"},
  {"PolyLog[3,1/2]", "PolyLog", {3, "1/2"}, PolyLog[3, 1/2], "polylog"},

  (* Bessel *)
  {"BesselJ[0,1]",  "BesselJ", {0, 1},    BesselJ[0, 1],  "bessel"},
  {"BesselJ[1,1]",  "BesselJ", {1, 1},    BesselJ[1, 1],  "bessel"},
  {"BesselY[0,1]",  "BesselY", {0, 1},    BesselY[0, 1],  "bessel"},

  (* Airy. DataLab "Airy" maps to mpmath.airyai (Ai). *)
  {"Airy[0]",       "Airy",   {0},        AiryAi[0],      "airy"},
  {"Airy[1]",       "Airy",   {1},        AiryAi[1],      "airy"}
};

(* ------------------------------------------------------------------ *)
(* Emit JSON                                                           *)
(* ------------------------------------------------------------------ *)
metadata = StringJoin[
  "  \"metadata\": {",
  "\n    \"generator\": \"tests/fixtures/mathematica_reference/special_functions/generate.wls\",",
  "\n    \"mathematica_version\": ", EscapeJsonString[ToString[$Version]], ",",
  "\n    \"precision_digits\": 50,",
  "\n    \"description\": \"DataLab whitelist functions vs Mathematica reference values.\"",
  "\n  }"
];

casesJson = StringJoin[
  "  \"cases\": [\n",
  StringRiffle[Map[CaseEntry @@ # &, cases], ",\n"],
  "\n  ]"
];

Print["{"];
Print[metadata, ","];
Print[casesJson];
Print["}"];
