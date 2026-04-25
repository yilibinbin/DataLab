#!/usr/bin/env wolframscript
(* Generate statistics ground truth: weighted means, sample/population
   means, and their standard errors, computed at 50-digit precision in
   Mathematica. DataLab's statistics_utils.compute_statistics should
   match these to ≥30 digits for ``mean`` and ``weighted_sigma`` modes.
*)

DigitString[x_] := Module[{n, rd, digits, expPos, signStr, mantStr, lenDigits},
  n = N[x, 50];
  If[n == 0, Return["0"]];
  signStr = If[n < 0, "-", ""];
  rd = RealDigits[Abs[n], 10, 50];
  If[!ListQ[rd] || Length[rd] != 2 || !ListQ[First[rd]],
    Return["RealDigits-failed-for-" <> ToString[InputForm[x]]]
  ];
  {digits, expPos} = rd;
  lenDigits = Length[digits];
  mantStr = StringJoin[ToString /@ digits];
  Which[
    expPos <= 0, signStr <> "0." <> StringJoin[Table["0", {-expPos}]] <> mantStr,
    expPos >= lenDigits, signStr <> mantStr <> StringJoin[Table["0", {expPos - lenDigits}]],
    True, signStr <> StringTake[mantStr, expPos] <> "." <> StringDrop[mantStr, expPos]
  ]
]

EscapeJsonString[s_] := StringJoin[
  "\"", StringReplace[s, {"\\" -> "\\\\", "\"" -> "\\\""}], "\""
]

JsonNum[x_] := EscapeJsonString[DigitString[x]]
JsonNumList[xs_] := StringJoin["[", StringRiffle[Map[JsonNum, xs], ", "], "]"]

(* Parse a fixture input. ALL fixture inputs MUST be either integers
   or exact rationals (e.g. ``"314/100"`` not ``"3.14"``) so the
   downstream arithmetic stays exact through Mathematica's symbolic
   layer. Final numericalisation is done by ``N[..., 50]`` at the
   point of JSON output, NOT here.

   ToExpression["1/2"] returns the exact ``Rational[1, 2]``, which
   feeds cleanly into ArithMean / WeightedMean / WeightedSampleStd
   without any precision-loss surprises. *)
ParseRational[v_] := If[StringQ[v], ToExpression[v], v]

(* ------------------------------------------------------------------ *)
(* Statistics formulas                                                 *)
(* ------------------------------------------------------------------ *)

(* Arithmetic mean *)
ArithMean[xs_List] := Total[xs] / Length[xs]

(* Sample (n-1) and population (n) variance *)
SampleVar[xs_List] := Module[{m = ArithMean[xs], n = Length[xs]},
  Total[(xs - m)^2] / (n - 1)
]
PopulationVar[xs_List] := Module[{m = ArithMean[xs], n = Length[xs]},
  Total[(xs - m)^2] / n
]

(* Weighted mean with sigmas (weights = 1/sigma^2) *)
WeightedMean[xs_List, sigmas_List] := Module[{w},
  w = Table[1/sigmas[[i]]^2, {i, Length[xs]}];
  Total[xs * w] / Total[w]
]

(* Standard error of the weighted mean: 1/Sqrt[Sum w_i] *)
WeightedSE[sigmas_List] := Module[{w},
  w = Table[1/sigmas[[i]]^2, {i, Length[sigmas]}];
  1 / Sqrt[Total[w]]
]

(* Weighted sample standard deviation, matching DataLab's
   ``compute_statistics`` formula (Kish-style effective DOF):

     numer = Sum_i w_i * (x_i - mu_w)^2
     dof   = W - W2/W           (effective degrees of freedom)
     var   = numer / dof
     std   = sqrt(var)

   where W = Sum w_i, W2 = Sum w_i^2.

   This differs from the textbook ``Sum w * delta^2 / (n-1)``
   formula — DataLab's choice corrects for the *effective* number
   of independent observations under non-uniform weighting, which
   is the right thing for Σ-weighted least-squares. The fixture
   must match DataLab's choice or the comparison is meaningless. *)
WeightedSampleStd[xs_List, sigmas_List] := Module[
  {w, W, W2, mu, n, dof, numer, var},
  n = Length[xs];
  If[n <= 1, Return[0]];
  w = Table[1/sigmas[[i]]^2, {i, n}];
  W = Total[w];
  W2 = Total[w^2];
  mu = Total[xs * w] / W;
  numer = Total[w * (xs - mu)^2];
  dof = W - W2/W;
  var = numer / dof;
  Sqrt[var]
]

(* ------------------------------------------------------------------ *)
(* Cases                                                                *)
(* ------------------------------------------------------------------ *)

(* Each case is a tuple: {id, mode, values (rationals), sigmas (rationals or all-Null)} *)
cases = {
  {"mean_sample_simple",
   "mean_sample",
   {1, 2, 3, 4, 5},
   Null},

  {"mean_population_simple",
   "mean_population",
   {1, 2, 3, 4, 5},
   Null},

  (* Use exact rationals (314/100 etc.) rather than decimal-string
     literals: SetPrecision on "3.14" can't recover the digits beyond
     IEEE 754 double precision, so the resulting "high-precision"
     value is misleading. Rationals stay exact through all the
     arithmetic. *)
  {"mean_sample_decimals",
   "mean_sample",
   {"314/100", "271/100", "141/100", "173/100", "162/100"},
   Null},

  {"mean_sample_n_one",
   "mean_sample",
   {42},
   Null},

  {"weighted_uniform",
   "weighted_sigma",
   {10, 11, 12, 13, 14},
   {"1/2", "1/2", "1/2", "1/2", "1/2"}},

  {"weighted_varied_sigmas",
   "weighted_sigma",
   {100, 101, 99, "201/2", "501/5"},
   {"1/10", "1/5", "1/4", "1/8", "1/12"}},

  {"weighted_two_points",
   "weighted_sigma",
   {1, 2},
   {"1/10", "1/20"}}
};

CaseEntry[id_, mode_, valsRaw_, sigmasRaw_] := Module[
  {vals, sigmas, mean, stddev, stdMean, sigmasJson},
  vals = Map[ParseRational, valsRaw];
  If[mode == "mean_sample" || mode == "mean_population",
    mean = ArithMean[vals];
    stddev = If[Length[vals] > 1,
      If[mode == "mean_sample",
        Sqrt[SampleVar[vals]],
        Sqrt[PopulationVar[vals]]],
      0];
    stdMean = If[Length[vals] > 1, stddev / Sqrt[Length[vals]], stddev];
    sigmas = {}; sigmasJson = "null",
    (* weighted *)
    sigmas = Map[ParseRational, sigmasRaw];
    mean = WeightedMean[vals, sigmas];
    stdMean = WeightedSE[sigmas];
    stddev = WeightedSampleStd[vals, sigmas];
    sigmasJson = JsonNumList[sigmas]
  ];
  StringJoin[
    "    {",
    "\n      \"id\": ", EscapeJsonString[id], ",",
    "\n      \"mode\": ", EscapeJsonString[mode], ",",
    "\n      \"values\": ", JsonNumList[vals], ",",
    "\n      \"sigmas\": ", sigmasJson, ",",
    "\n      \"expected_mean\": ", JsonNum[N[mean, 50]], ",",
    "\n      \"expected_std\": ", JsonNum[N[stddev, 50]], ",",
    "\n      \"expected_std_mean\": ", JsonNum[N[stdMean, 50]],
    "\n    }"
  ]
]

caseLines = Map[CaseEntry @@ # &, cases];

metadata = StringJoin[
  "  \"metadata\": {",
  "\n    \"generator\": \"tests/fixtures/mathematica_reference/statistics/generate.wls\",",
  "\n    \"mathematica_version\": ", EscapeJsonString[ToString[$Version]], ",",
  "\n    \"precision_digits\": 50,",
  "\n    \"description\": \"Sample/population/weighted-mean reference values.\"",
  "\n  }"
];

casesJson = StringJoin[
  "  \"cases\": [\n",
  StringRiffle[caseLines, ",\n"],
  "\n  ]"
];

Print["{"];
Print[metadata, ","];
Print[casesJson];
Print["}"];
