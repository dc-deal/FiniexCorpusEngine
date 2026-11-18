---
contract: page/1
work: openstax-finance-2e
pdf_page: 446
image_size: "1688x2184"
printed_label: "432"
label_position: header
page_kind: body
columns: 1
rotation: 0
language: en
---

::: {#b01 .page_number bbox="135 66 169 98"}
432
:::

::: {#b02 .page_header bbox="169 66 557 98"}
14 • Regression Analysis in Finance
:::

::: {#b03 .code kind=console lang=r cont=prev bbox="194 192 1131 1055"}
Residuals:
1 2 3 4 5 6 7
-0.5672 -0.5188 -1.6547 -0.3828 1.9375 2.2969 -1.1109
Coefficients:
Estimate Std. Error t value Pr(>|t|)
(Intercept) -0.3453 0.7836 -0.441 0.67783
SP500 0.8641 0.1734 4.984 0.00416 **
---
Signif. codes: 0 ‘***’ 0.001 ‘**’ 0.01 ‘*’ 0.05 ‘.’ 0.1 ‘ ’ 1
Residual standard error: 1.658 on 5 degrees of freedom
Multiple R-squared: 0.8325, Adjusted R-squared: 0.7989
F-statistic: 24.84 on 1 and 5 DF, p-value: 0.004161
:::

::: {#b04 .paragraph bbox="194 1075 1485 1158"}
In this output, the y-intercept and slope is given, as well as the residuals for each x-value. The output includes additional statistical details regarding the regression analysis.
:::

::: {#b08 .paragraph bbox="194 1223 1485 1341"}
First, we can create a structure in R called a data frame to hold the values of the independent variable for which we want to generate a prediction. For example, we would like to generate the predicted return for Coca-Cola stock, given that the return for the S&P 500 is 6.
:::

::: {#b11 .code kind=console lang=r bbox="194 1546 608 1813"}
> a <- data.frame(SP500=6)
> predict(model, a)
1
4.839062
:::

::: {#b15 .page_footer bbox="194 2086 523 2123"}
Access for free at openstax.org
:::
