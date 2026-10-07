"""Every failure the review can hit, as one table: a code, a plain message and the exact fix.

Standard library only. review.py raises ReviewError(code, **fields); the message
and fix are filled from the fields. Each code has its own exit status, so a
caller can tell the failures apart without reading the text.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

RECIPE = "creative-context/references/export-recipe.md"
INPUTS = "creative-context/references/data-inputs.md"
INSTALL = "claude plugin install jumbo-creative@jumbo-creative-skills (or npx skills add adamsz-er/jumbo-creative-skills)"

# code -> (exit status, message, fix); {fields} are filled by the caller
TABLE: Dict[str, Tuple[int, str, str]] = {
    "E-NODATA": (10, "There is no ad data to review yet{where}.",
                 "Pick one: (1) add --demo to see a sample account first; (2) connect Meta's ads connector and say "
                 "'review my Meta ads'; (3) export your ads as a daily CSV: " + RECIPE + " steps 1 to 4 "
                 "(Ads tab, add the columns, Breakdown > By time > Day, Export as CSV), then pass the file."),
    "E-COLUMNS": (11, "{path} is missing {count} column{plural} the review needs: {columns}.",
                  "{steps} Re-export with those columns, or pass the file again once they are in."),
    "E-EMPTY": (12, "{what}", "{how}"),
    "E-RECONCILE": (13, "The pull is incomplete: {problems}.",
                    "Re-run the pull with pagination so every ad is fetched (including archived ads that delivered in the "
                    "window); see " + INPUTS + " steps 3 to 7. Then run the pull again."),
    "E-CURRENCY": (14, "The data does not say which currency the money is in.",
                   "Pass --currency followed by your three-letter code (for example --currency USD), or add 'currency: USD' "
                   "to the Script settings of your creative-profile.md."),
    "E-SKILL": (15, "The skill '{skill}' is not installed next to creative-review, and the review needs it.",
                "Install the whole package: " + INSTALL + "."),
    "E-PROFILE": (16, "The profile {path} could not be read: {reason}.",
                  "Fix the line named above in {path}, or pass a different --profile."),
    "E-TARGET": (17, "{detail}",
                 "Write targets as metric=number, for example --target cpa=40,roas=3. Accepted metrics: {metrics}."),
    "E-REPORT": (18, "The dashboard was written but did not pass its own structure check: {problem}.",
                 "Run the review again; if it repeats, rerun with --debug and report the line above."),
    "E-ANALYSIS": (19, "The {step} step stopped: {detail}.",
                   "Fix what that line says and run the review again. Everything before this step is kept in {folder}."),
}

UNEXPECTED_EXIT = 1


class ReviewError(Exception):
    """A known failure: a code from TABLE plus the fields its message and fix use."""

    def __init__(self, code: str, **fields: Any) -> None:
        super().__init__(code)
        self.code, self.fields = code, fields

    @property
    def exit_status(self) -> int:
        return TABLE[self.code][0]

    @property
    def message(self) -> str:
        return TABLE[self.code][1].format(**self.fields)

    @property
    def fix(self) -> str:
        return TABLE[self.code][2].format(**self.fields)

    def render(self) -> str:
        return "%s %s\nHow to fix it: %s" % (self.code, self.message, self.fix)


def empty_window_error(window: str, covers: str) -> ReviewError:
    return ReviewError("E-EMPTY", what="There are no ad rows to review in %s. The file covers %s." % (window, covers),
                       how="Re-export with a date range that overlaps your window (step 1 of %s), or drop --from and --to." % RECIPE)


def empty_filter_error(where: Any) -> ReviewError:
    return ReviewError("E-EMPTY", what="Your filter %s kept no ads." % ", ".join(where or []),
                       how="Check the field and value against your data, or drop --where.")


def nodata_error(path: Any = None) -> ReviewError:
    return ReviewError("E-NODATA", where=": %s does not exist" % path if path else "")


COLUMN_STEPS = {
    "date": "Set Breakdown to By time > Day (step 3 of " + RECIPE + ").",
    "ad name": "Add Ad name in Customize columns (step 2 of " + RECIPE + ").",
    "spend": "Add Amount spent in Customize columns (step 2 of " + RECIPE + ").",
    "impressions": "Add Impressions in Customize columns (step 2 of " + RECIPE + ").",
}


def columns_error(path: str, missing: Any) -> ReviewError:
    missing = list(missing)
    return ReviewError("E-COLUMNS", path=path, count=len(missing), plural="" if len(missing) == 1 else "s",
                       columns=", ".join(missing), steps=" ".join(COLUMN_STEPS[m] for m in missing))


def unexpected_text(error: BaseException) -> str:
    one_line = (str(error) or type(error).__name__).splitlines()[0]
    return "Something unexpected went wrong: %s: %s\nRerun with --debug for details." % (type(error).__name__, one_line)
