# notes

## Page 1

# Introduction to Machine Learning Class Notes
## Huy Nguyen
## PhD Student, Human-Computer Interaction Institute
## Carnegie Mellon University

---

## Page 2

# Contents
Preface 3
1 MLE and MAP 4
1.1 MLE . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4
1.2 Bayesian learning and MAP . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 5
2 Nonparametric models: KNN and kernel regression 7
2.1 Bayes decision rule . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 7
2.2 Classification . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 8
2.3 K-nearest neighbors . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 8
2.4 Local Kernel Regression . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 9
3 Linear Regression 11
3.1 Basic linear regression . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 11
3.2 Multivariate and general linear regression . . . . . . . . . . . . . . . . . . . . . . 12
3.3 Regularized least squares . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 13
3.3.1 Definition . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 13
3.3.2 Connection to MLE and MAP . . . . . . . . . . . . . . . . . . . . . . . . 14
4 Logistic Regression 16
4.1 Definition . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 16
4.2 Training logistic regression . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 17
5 Naive Bayes Classifier 20
5.1 Gaussian Bayes . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 20
5.2 Naive Bayes Classifier . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 21
5.3 Text classification: bag of words model . . . . . . . . . . . . . . . . . . . . . . . 23
5.4 Generative vs Discriminative Classifer . . . . . . . . . . . . . . . . . . . . . . . . 23
6 Neural Networks and Deep Learning 25
6.1 Definition . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 25
6.2 Training a neural network . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 26
6.2.1 Gradient descent . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 26
6.2.2 Backpropagation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 28
6.3 Convolutional neural networks . . . . . . . . . . . . . . . . . . . . . . . . . . . . 30
6.3.1 Convolutional Layer . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 31
6.3.2 Pooling layer . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 32
6.3.3 Fully Connected Layer . . . . . . . . . . . . . . . . . . . . . . . . . . . . 32
1

---

## Page 3

7 Support Vector Machine 33
7.1 Introduction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 33
7.2 Primal form . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 34
7.2.1 Linearly separable case . . . . . . . . . . . . . . . . . . . . . . . . . . . . 34
7.2.2 Non linearly separable case . . . . . . . . . . . . . . . . . . . . . . . . . . 36
7.3 Dual representation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 36
7.3.1 Linearly separable case . . . . . . . . . . . . . . . . . . . . . . . . . . . . 36
7.3.2 Transformation of inputs . . . . . . . . . . . . . . . . . . . . . . . . . . . 38
7.3.3 Kernel tricks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 40
7.3.4 Non linearly separable case . . . . . . . . . . . . . . . . . . . . . . . . . . 41
7.4 Other topics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 41
7.4.1 Why do SVMs work? . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 41
7.4.2 Multi-class classification with SVM . . . . . . . . . . . . . . . . . . . . . 41
8 Ensemble Methods and Boosting 42
8.1 Introduction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 42
8.2 Mathematical details . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 45
8.2.1 What αt to choose for hypothesis ht? . . . . . . . . . . . . . . . . . . . . 45
8.2.2 Show that training error converges to 0 . . . . . . . . . . . . . . . . . . . 46
9 Principal Component Analysis 49
9.1 Introduction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 49
9.2 PCA algorithms . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 50
9.3 PCA applications . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 51
9.3.1 Eigenfaces . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 51
9.3.2 Image compression . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 53
9.4 Shortcomings . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 53
10 Hidden Markov Model 54
10.1 Introduction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 54
10.2 Inference in HMM . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 55
10.2.1 What is P (qt = si)? . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 56
10.2.2 What is P (qt = si | o1o2 . . . ot)? . . . . . . . . . . . . . . . . . . . . . . . 57
10.2.3 What is arg max
q1q2...qt
P (q1q2 . . . qt | o1o2 . . . ot)? . . . . . . . . . . . . . . . . . 57
11 Reinforcement Learning 59
11.1 Markov decision process . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 59
11.2 Reinforcement learning - No action . . . . . . . . . . . . . . . . . . . . . . . . . 60
11.2.1 Supervised RL . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 61
11.2.2 Certainty-Equivalence learning . . . . . . . . . . . . . . . . . . . . . . . . 62
11.2.3 Temporal difference learning . . . . . . . . . . . . . . . . . . . . . . . . . 63
11.3 Reinforcement learning with action - Policy learning . . . . . . . . . . . . . . . . 64
12 Generalization and Model Selection 66
12.1 True risk vs Empirical risk . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 66
12.2 Model Selection . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 68
2

---

## Page 4

# Preface
This is the class notes I took for CMU’s 10701: Introduction to Machine Learning in Fall 2018.
The goal of this document is to serve as a quick review of key points from each topic covered in
the course. A more comprehensive note collection for beginners is available at UPenn’s CIS520:
Machine Learning.
In this document, each chapter typically covers one machine learning methodology and contains
the followings:
- Definition - definition of important concepts.
- Diving in the Math - mathematical proof for a statement / formula.
- Algorithm - the steps to perform a common routine / subroutine.
Intertwined with these components are transitional text (as I find them easier to review than
bullet points), so the document as a whole ends up looking like a mini textbook. While there
are already plenty of ML textbooks out there, I am still interested in writing up something
that stays closest to the content taught by Professor Ziv Bar-Joseph and Pradeep Ravikumar.
I would also like to take this opportunity to thank the two professors for their guidance.
3

---

## Page 5

# Chapter 1
# MLE and MAP
## 1.1 MLE
Definition 1: (Likelihood function and MLE)
Given n data points x1, x2, . . . , xn we can define the likelihood of the data given the model
θ (usually a collection of parameters) as follows.
ˆP (dataset | θ) =
n∏
k=1
ˆP (xk | θ). (1.1)
The maximum likelihood estimate (MLE) of θ is
ˆθM LE = arg max
θ
ˆP (dataset | θ). (1.2)
To determine the values for the parameters in θ, we maximize the probability of generating the
observed samples. For example, let θ be the model of a coin flip (so θ = {P (Head) = q}), then
the best assignment (MLE) for θ in this case is ˆθ =
{
ˆq =
# heads
# samples
}
.
Diving in the Math 1 - MLE for binary variable
For a binary random variable A with P (A = 1) = q, we show that ˆq =
# 1
# samples .
Assume we observe n samples x1, x2, . . . , xn with n1 heads and n2 tails.
Then, the likelihood function is
P (D | θ) =
n∏
i=1
P (xi | θ) = q
n1 (1 − q)
n2 .
We now find ˆq that maximizes this likelihood function, i.e., ˆq = arg max
q
q
n1 (1 − q)
n2 .
To do so, we set the derivative to 0:
0 =
∂
∂q
q
n1 (1 − q)
n2 = n1q
n1−1(1 − q)
n2 − q
n1 n2(1 − q)
n2−1,
which is equivalent to
q
n1−1(1 − q)
n2−1(n1(1 − q) − qn2) = 0,
which yields
n1(1 − q) − qn2 = 0 ⇔ q =
n1
n1 + n2
4

---

## Page 6

When working with products, probabilities of entire datasets often get too small. A possible
solution is to use the log of probabilities, often termed log likelihood 1:
log ˆP (dataset | M ) = log
n∏
k=1
ˆP (xk | M ) =
n∑
k=1
log ˆP (xk | M ). (1.3)
In this case, the algorithm for MLE is as follows.
Algorithm 1: (Finding the MLE)
Given n data points x1, x2, . . . , xn and a model θ represented by an expression for P (X | θ),
perform the following steps:
1. Compute the log-likelihood
L = log
n∏
i=1
P (xi | θ) =
n∑
i=1
log P (xi | θ).
2. For each parameter γ in θ, find the solution(s) to the equation
∂L
∂γ = 0.
3. The solution ˆγ that satisfies
∂ 2L
∂ ˆγ 2 ≤ 0 is the MLE of γ.
## 1.2 Bayesian learning and MAP
We first note the Bayes formula
P (A | B) =
P (B | A)P (A)
P (B)
=
P (B | A)P (A)
∑
A
P (B | A)P (A)
. (1.4)
In Bayesian learning, prior information is encoded as a distribution over possible values of
parameters P (M ). Using (1.4), we get an updated posterior distribution over parameters. To
derive the estimate of true parameter, we choose the value that maximizes posterior probability.
Definition 2: (MAP)
Given a dataset and a model M with prior P (M ), the maximum a posteriori (MAP) estimate
of M is
ˆθM AP = arg max
θ
P (θ | dataset) = arg max
θ
P (dataset | θ)P (θ). (1.5)
1Note that because log t is monotonous on R, maximizing log t is the same as maximizing t.
5

---

## Page 7

If we only have very few samples, MLE may not yield accurate results, so it is useful to take into
account prior knowledge. When the number of samples gets large, the effect of prior knowledge
will diminish.
Similar to MLE, we have the following algorithm for MAP.
Algorithm 2: (Finding the MAP)
Given n data points x1, x2, . . . , xn, a model θ represented by an expression for P (X | θ), and
the prior knowledge P (θ), perform the following steps:
1. Compute the log-likelihood
L = log P (θ) ·
n∏
i=1
P (xi | θ) = log P (θ) +
n∑
i=1
log P (xi | θ).
2. For each parameter γ in θ, find the solution(s) to the equation
∂L
∂γ = 0.
3. The solution ˆγ that satisfies
∂ 2L
∂ ˆγ 2 ≤ 0 is the MAP of γ.
6

---

## Page 8

# Chapter 2
# Nonparametric models: KNN and
# kernel regression
## 2.1 Bayes decision rule
Classification is the task of predicting a (discrete) output label given the input data. The
performance of any classification algorithm depends on two factors: (1) the parameters are
correct, and (2) the underlying assumption holds. The most optimal algorithm is called the
Bayes decision rule.
Algorithm 3: (Bayes decision rule)
If we know the conditional probability P (x | y) and class prior P (y), use (1.4) to compute
P (y = i | x) =
P (x | y = i)P (y = i)
P (x)
∝ P (x | y = i)P (y = i) = qi(x) (2.1)
and qi(x) to select the appropriate class. Choose class 0 if q0(x) > q1(x) and 1 otherwise.
In general choose the class ˆc = arg max
c
{qc(x)}.
Because our decision is probabilistic, there is still chance for error. The Bayes error rate (risk)
of the data distribution is the probability an instance is misclassified by the Bayes decision rule.
For binary classification, the risk for sample x is
R(x) = min{P (y = 0 | x), P (y = 1 | x)}. (2.2)
In other words, if P (y = 0 | x) > P (y = 1 | x), then we would pick the label 0, and the risk is
the probability that the actual label is 1, which is P (y = 1 | x).
We can also compute the expected risk - the risk for the entire range of values of x:
E[r(x)] =
∫
x
r(x)P (x)dx
=
∫
x
min{P (y = 0 | x), P (y = 1 | x)}dx
= P (y = 0)
∫
L1
P (x | y = 0)dx + P (y = 1)
∫
L0
P (x | y = 1)dx,
where Li is the region over which the decision rule outputs label i.
The risk value we computed assumes that both errors (assigning instances of class 1 to 0 and
vice versa) are equally harmful. In general, we can set the weight penalty Li,j (x) for assigning
7

---

## Page 9

instances of class i to class j. This gives us the concept of a loss function
E[L] = L0,1(x)P (y = 0)
∫
L1
P (x | y = 0)dx + L1,0(x)P (y = 1)
∫
L0
P (x | y = 1)dx. (2.3)
## 2.2 Classification
There are roughly three types of classifiers:
1. Instance based classifiers: use observation directly (no models). Example: K nearest
neighbor.
2. Generative: build a generative statistical model. Example: Naive Bayes.
3. Discriminative: directly estimate a decision rule/boundary. Example: decision tree.
The classification task itself contains several steps:
1. Feature transformation: e.g, how do we encode a picture?
2. Model / classifier specification: What type of classifier to use?
3. Model / classifier estimation (with regularization): How do we learn the parameters
of our classifier? Do we have enough examples to learn a good model?
4. Feature selection: Do we really need all the features? Can we use a smaller number and
still achieve the same (or better) results?
Classification is one of the key components of supervised learning, where we provide the algorithm
with labels to some of the instances and the goal is to generalize so that a model / method can
be used to determine the labels of the unobserved examples.
## 2.3 K-nearest neighbors
A simple yet surprisingly efficient algorithm is K nearest neighbors.
Algorithm 4: (K-nearest neighbors)
Given n data points, a distance function d and a new point x to classify, select the class of
x based on the majority vote in the K closest points.
Note that this requires the definition of a distance function or similarity measure between sam-
ples. We also need to determine K beforehand. Larger K means the resulting classifier is more
‘smooth’ (but smoothness is primarily dependent on the actual distribution of the data).
From a probabilistic view, KNN tries to approximate the Bayes decision rule on a subset of data.
We compute P (x | y), P (y) and P (x) for some small region around our sample, and the size of
that region will be dependent on the distribution of the test sample.
8

---

## Page 10

Diving in the Math 2 - Computing probabilities for KNN
Let z be the new point we want to classify. Let V be the volume of the m dimensional ball
R around z containing the K nearest neighbors for z (where m is the number of features).
Also assume that the distribution in R is uniform.
Consider the probability P that a data point chosen at random is in R. On one hand,
because there are K points in R out of a total of N points, P =
K
N . On the other hand, let
P (x) = q be the density at a point x ∈ R (q is constant because R has uniform distribution).
Then P =
∫
x∈R
P (x)dx = qV . Hence we see that the marginal probability of z is
P (z) = q =
P
V
=
K
N V
.
Similarly, the conditional probability of z given a class i is
P (z | y = i) =
Ki
NiV
.
Finally, we compute the prior of class i:
P (y = i) =
Ni
N
.
Using Bayes formula:
P (y = i | z) =
P (z | y = i)P (y = i)
P (z)
=
Ki
K
.
Using the Bayes decision rule we will choose the class with the highest probability, which
corresponds to the class with the highest Ki - the number of samples in K.
## 2.4 Local Kernel Regression
Kernel regression is similar to KNN but used for regression. In particular, it focuses on a specific
region of the input, as opposed to the global space (like linear regression does). For example,
we can output the local average:
ˆf (x) =
∑n
i=1 yi · I (‖xi − x‖ ≤ h)
∑n
i=1 I (‖xi − x‖ ≤ h)
, (2.4)
which can also be expressed in a form similar to linear regression:
ˆf (x) =
n∑
i=1
wiyi, wi =
I (‖xi − x‖ ≤ h)
I
(∑n
j=1 ‖xj − x‖ ≤ h
) .
Note that the wi’s here represent a hard boundary: if Xi is close to x then wi = 1, else wi = 0.
In the general case, w can be expressed using kernel functions.
9

---

## Page 11

Algorithm 5: (Nadaraya-Watson Kernel Regression)
Given n data points {(xi, yi)}n
i=1, we can output the value at a new point x as
ˆf (x) =
n∑
i=1
wiyi, wi =
K
(∣
∣ x−xi
h
∣
∣
)
∑n
j=1 K
(∣
∣ x−xi
h
∣
∣
) , (2.5)
where K is a kernel function. Some typical kernel functions include:
- Boxcar kernel: K(t) = I (t ≤ 1).
- Gaussian kernel: K(t) =
1
√
2π
exp
(
−
t2
2
)
.
The distance h in this case the called the kernel bandwidth. The choice of h should depend
on the number of training data (determines variance) and smoothness of function (determines
bias).
- Large bandwidth averages more data points so reduces noice (lower variance).
- Small bandwidth fits more accurately (lower bias).
In general this is the bias-variance tradeoff. Bias represents how accurate the result is (lower
bias = more accurate). Variance represents how sensitive the algorithm is to changes in the
input (lower variance = less sensitive). Here a large bandwidth (h = 200) yields low variance
and high bias, while a small bandwidth (h = 1) yields high variance and low bias. In this case,
h = 50 seems like the best middle ground.
10

---

## Page 12

# Chapter 3
# Linear Regression
## 3.1 Basic linear regression
Definition 3: (Linear Regression)
Given an input x we would like to compute an output y as
y = wx + ,
where w is a parameter and  represents measurement of noise.
Our goal is to estimate w from training data of (xi, yi) pairs. One way is to find the least square
error (LSE)
ˆwLR = arg min
w
∑
i
(yi − wxi)
2 (3.1)
which minimizes squared distance between measurements and predicted lines. LSE has a nice
probabilistic interpretation (as we will see shortly, if  ∼ N (0, σ2) then ˆw is MLE of w). and is
easy to compute. In particular, the solution to (3.1) is
ˆw =
∑
i xiyi∑
i x2
i
. (3.2)
Diving in the Math 3 - Solving linear regression using LSE
We take the derivative w.r.t w and set to 0:
0 =
∂
∂w
∑
i
(yi − wxi)
2 = −2
∑
i
xi(yi − wxi),
which yields
∑
i
xiyi =
∑
i
wx
2
i ⇒ w =
∑
i xiyi∑
i x2
i
If the line does not pass through the origin, simply change the model to
y = w0 + w1x + ,
and following the same process gives
w0 =
∑
i yi − w1xi
n
, w1 =
∑
i xi(yi − w0)
∑
i x2
i
. (3.3)
11

---

## Page 13

## 3.2 Multivariate and general linear regression
If we have several inputs, this becomes a multivariate regression problem:
y = w0 + w1x1 + . . . + wkxk + .
However, not all functions can be approximated using the input values directly. In some cases we
would like to use polynomial or other terms based on the input data. As long as the coefficients
are linear, the equation is still a linear regression problem. For instance,
y = w0x1 + w1x
2
1 + . . . + wkx
2
k + .
Typical non-linear basis functions include:
- Polynomial φj (x) = xj ,
- Gaussian φj (x) =
(x−μj )2
2σ2
j
,
- Sigmoid φj (x) =
1
1+exp(−sj x) .
Using this new notation, we formulate the general linear regression problem:
y =
∑
j
wj φj (x),
where φj (x) can either be xj for multivariate regression or one of the non-linear bases we defined.
Now assume the general case where we where have n data points
(x(1), y(1)), (x(2), y(2)), . . . , (x(n), y(n)), and each data point has k features (recall that feature j of
x(i) is denoted x
(i)
j ). Again using LSE to find the optimal solution, by defining
Φ =





φ0(x(1)) φ1(x(1)) . . . φk(x(1))
φ0(x(2)) φ1(x(2)) . . . φk(x(2))
...
... . . .
...
φ0(x(n)) φ1(x(n)) . . . φk(x(n))





=




— φ(x(1))T —
— φ(x(2))T —
. . .
— φ(x(n))T —



 , (3.4)
we then get
w = (Φ
T Φ)
−1Φ
T y. (3.5)
Diving in the Math 4 - LSE for general linear regression problem
Our goal is to minimize the following loss function:
J (w) =
∑
i
(y
(i) −
∑
j
wj φj (x
(i)))
2 =
∑
i
(y
(i) − w
T φ(x
(i)))
2,
where w and φ(x(i)) are vectors of dimension k + 1 and y(i) is a scalar.
Setting the derivative w.r.t w to 0:
0 =
∂
∂w
∑
i
(y
(i) − w
T φ(x
(i)))
2 = 2
∑
i
(y
(i) − w
T φ(x
(i)))φ(x
(i))
T ,
which yields ∑
i
y
(i)φ(x
(i))
T = w
T ∑
i
φ(x
(i))φ(x
(i))
T .
Hence, defining Φ as in (3.4) would give us
(Φ
T Φ)w = Φ
T y ⇒ w = (Φ
T Φ)
−1Φ
T y
12

---

## Page 14

To sum up, we have the following algorithm for the general linear regression problem.
Algorithm 6: (General linear regression algorithm)
Input: Given n input data {(x(i), y(i))}n
i=1 where x(i) is 1 × m and y(i) is scalar, as well as
m basis functions {φj }m
j=1, we find
ˆw = arg min
w
n∑
i=1
(y
(i) − w
T φ(x
(i)))
2
by the following procedure:
1. Compute Φ as in (3.4).
2. Output ˆw = (ΦT Φ)−1ΦT y.
## 3.3 Regularized least squares
## 3.3.1 Definition
In the previous chapter we see that a linear regression problem involves solving (ΦT Φ)w = ΦT y
for w. If ΦT Φ is invertible, we would get w = (ΦT Φ)−1ΦT y as in (3.5). Now what if ΦT Φ is not
invertible?
Recall that full rank matrices are invertible, and that
rank(Φ
T Φ) = the number of non-zero eigenvalues of Φ
T Φ
≤ min(n, k) since Φ is n × k
In other words, ΦT Φ is not invertible if n < k, i.e., there are more features than data point. More
specifically, we have n equations and k > n unknowns - this is an undetermined system of linear
equations with many feasible solutions. In that case, the solution needs to be further constrained.
One way, for example, is Ridge Regression - using L2 norm as penalty to bias the solution to
“small” values of w (so that small changes in input don’t translate to large changes in output):
ˆwRidge = arg min
w
n∑
i=1
(yi − xiw)
2 + λ ‖w‖
2
2
= arg min
w
(Φw − y)
T (Φw − y) + λ ‖w‖
2
2 , λ ≥ 0
= (Φ
T Φ + λI)
−1Φ
T y. (3.6)
We could also use Lasso Regression (L1 penalty)
ˆwLasso = arg min
w
n∑
i=1
(yi − xiw)
2 + λ ‖w‖1 , (3.7)
which biases towards many parameter values being zero - in other words, many inputs become
irrelevant to prediction in high-dimensional settings. There is no closed form solution for (3.7),
but it can be optimized by sub-gradient descent.
13

---

## Page 15

In general, we can phrase the problem as finding
ˆw = arg min
w
(Φw − y)
T (Φw − y) + λpen(w), (3.8)
where pen(w) is a penalty function. Here’s a visualization for different kinds of penalty functions:
## 3.3.2 Connection to MLE and MAP
Consider a linear regression problem
Y = ˆf (X) +  = X ˆw + ,
where the noise  ∼ N (0, σ2I), which implies Y ∼ N (X ˆw, σ2I). If ΦT Φ is invertible, then w
can be determined exactly by MCLE:
ˆwM CLE = arg max
w
P ({yi}
n
i=1 | w, σ
2, {xi}
n
i=1)
︸ ︷︷ ︸
Conditional log likelihood
= arg min
w
n∑
i=1
(xiw − yi)
2 = ˆwLR, (3.9)
where the last equality follows from (3.1). In other words, Least Square Estimate is the same as
MCLE under a Gaussian model.
In case ΦT Φ is not invertible, we can encode the Ridge bias by letting w ∼ N (0, τ 2I) and
P (w) ∝ exp(−wT w/2τ 2), which would yield
ˆwM CAP = arg max
w
P ({yi}
n
i=1 | w, σ
2, {xi}
n
i=1)
︸ ︷︷ ︸
Conditional log likelihood
+ log P (w)
︸ ︷︷ ︸
log prior
= arg min
w
n∑
i=1
(xiw − yi)
2 + λ ‖w‖
2
2 = ˆwRidge, (3.10)
where λ is constant in terms of σ2 and τ 2, and the last equality follows from (3.6). In other
words, Prior belief that w is Gaussian with mean 0 biases solution to “small” w.
14

---

## Page 16

Diving in the Math 5 - Ridge regression and MCAP
Since we are given P (w) ∝ exp(−wT w/2τ 2), let P (w) = exp(−c ‖w‖
2
2), where c is some
constant, then − log P (w) = c ‖w‖
2
2, so (3.10) is equivalent to finding
inf
w
{L(w) + c ‖w‖
2
2}
= inf
w
{L(w)} such that ‖w‖
2
2 ≤ L(c),
where L(c) is a bijective function of c. So adding c ‖w‖
2
2 is the same as the ridge regression
constraint ‖w‖
2
2 ≤ L for some constant L.
Similarly, we can encode the Lasso bias by letting wi ∼ Laplace(0, t) (iid) and P (wi) ∝
exp(−|wi|/t), which would yield
ˆwM CAP = arg max
w
P ({yi}
n
i=1 | w, σ
2, {xi}
n
i=1)
︸ ︷︷ ︸
Conditional log likelihood
+ log P (w)
︸ ︷︷ ︸
log prior
= arg min
w
n∑
i=1
(xiw − yi)
2 + λ ‖w‖1 = ˆwLasso, (3.11)
where λ is constant in terms of σ2 and t, and the last equality follows from (3.7). In other words,
Prior belief that w is Laplace with mean 0 biases solution to “sparse” w.
15

---

## Page 17

# Chapter 4
# Logistic Regression
## 4.1 Definition
We know that regression is for predicting real-valued output Y , while classification is for pre-
dicting (finite) discrete-valued Y . But is there a way to connect regression to classification? Can
we predict the “probability” of a class label? The answer is generally yes, but we have to keep
in mind the constraint that the probability value should lie in [0, 1].
Definition 4: (Logistic Regression)
Assume the following functional form for P (Y | X):
P (Y = 1 | X) =
1
1 + exp(−(w0 +
∑
i wiXi))
, (4.1)
P (Y = 0 | X) =
1
1 + exp(w0 +
∑
i wiXi)
. (4.2)
In essence, logistic regression means applying the logistic function σ(z) =
1
1+exp(−z) to a linear
function of the data. However, note that it is still a linear classifier.
Diving in the Math 6 - Logistic Regression as linear classifier
Note that P (Y = 1 | X) can be rewritten as
P (Y = 1 | X) =
exp(w0 +
∑
i wiXi)
1 + exp(w0 +
∑
i wiXi)
.
We would assign label 1 if P (Y = 1 | X) > P (Y = 0 | X), which is equivalent to
exp(w0 +
∑
i
wiXi) > 1 ⇔ w0 +
∑
i
wiXi > 0.
Similarly, we would assign label 0 if P (Y = 1 | X) < P (Y = 0 | X), which is equivalent to
exp(w0 +
∑
i
wiXi) < 1 ⇔ w0 +
∑
i
wiXi < 0.
In other words, the decision boundary is the line w0 +
∑
i wiXi, which is linear.
16

---

## Page 18

## 4.2 Training logistic regression
Given training data {(xi, yi)}n
i=1 where the input has d features, we want to learn the parameters
w0, w1, . . . , wd. We can do so by MCLE:
ˆwM CLE = arg max
w
n∏
i=1
P (y
(i) | x
(i), w). (4.3)
Note the Discriminative philosophy: don’t waste effort learning P (X), focus on P (Y | X) - that’s
all that matters for classification! Using (4.1) and (4.2), we can then compute the log-likelihood:
l(w) = ln
(
n∏
i=1
P (y
(i) | x
(i), w)
)
=
n∑
i=1
[
y
(i)(w0 +
d∑
j=1
wix
(i)
j ) − ln(1 + exp(w0 +
d∑
j=1
wix
(i)
j ))
]
. (4.4)
There is no closed-form solution to maximize l(w), but we note that it is a concave function.
Definition 5: (Concave function)
A function l(w) is called concave if the line joining two points l(w1), l(w2) on the function
does not lie above the function on the interval [w1, w2].
Equivalently, a function l(w) is concave on [w1, w2] if
l(tx1 + (1 − t)x2) ≥ tl(x1) + (1 − t)l(x2)
for all x1, x2 ∈ [w1, w2] and t ∈ [0, 1]. If the sign is reversed, l is a convex function.
17

---

## Page 19

Diving in the Math 7 - Log likelihood of logistic regression is concave
For convenience we denote x
(i)
0 = 1, so that w0 +
∑d
i=j wix
(i)
j = wT x(i).
We first note the following lemmas:
1. If f is convex then −f is concave and vice versa.
2. A linear combination of n convex (concave) functions f1, f2, . . . , fn with nonnegative
coefficients is convex (concave).
3. Another property of twice differentiable convex function is that the second derivative
is nonnegative. Using this property, we can see that f (x) = log(1 + exp x) is convex.
4. If f and g are both convex, twice differentiable and g is non-decreasing, then g ◦ f is
convex.
Now we rewrite l(w) as follows:
l(w) =
n∑
i=1
y
(i)w
T x
(i) − log(1 + exp(w
T x
(i)))
=
n∑
i=1
y
(i)w
T x
(i) −
n∑
i=1
log(1 + exp(w
T x
(i)))
=
n∑
i=1
y
(i)fi(w) −
n∑
i=1
g(fi(w)),
where fi(w) = wT x(i) and g(z) = log(1 + exp z).
fi(w) is of the form Ax + b where A = x(i) and b = 0, which means it’s affine (i.e., both
concave and convex). We also know that g(z) is convex, and it’s easy to see g is non-
decreasing. This means g(fi(w)) is convex, or equivalently, −g(fi(w)) is concave.
To sum up, we can express l(w) as
l(w) =
n∑
i=1
y
(i)fi(w)
︸ ︷︷ ︸
concave
+
n∑
i=1
−g(fi(w))
︸ ︷︷ ︸
concave
,
hence l(w) is concave.
As such, it can be optimized by the gradient ascent algorthim.
Algorithm 7: (Gradient ascent algorithm)
Initialize: Pick w at random.
Gradient:
∇wE(w) =
(
∂E(w)
∂w0
,
∂E(w)
∂w1
, . . . ,
∂E(w)
∂wd
)
.
Update:
∆w = η∇wE(w)
w
(t+1)
t ← w
(t)
i + η
∂E(w)
∂wi
,
where η > 0 is the learning rate.
18

---

## Page 20

In this case our likelihood function is specified in (4.4), so we have the following steps for training
logistic regression:
Algorithm 8: (Gradient ascent algorithm for logistic regression)
Initialize: Pick w at random and a learning rate η.
Update:
- Set an  > 0 and denote
ˆP (y
(i) = 1 | x
(i), w
(t)) =
exp(w
(t)
0 +
∑d
j=1 w
(t)
j x
(i)
j )
1 + exp(w
(t)
0 +
∑d
j=1 w
(t)
j x
(i)
j )
.
- Iterate until |w
(t+1)
0 − w
(t)
0 | < :
w
(t+1)
0 ← w
(t)
0 + η
n∑
i=1
[
y
(i) − ˆP (y
(i) = 1 | x
(i), w
(t))
]
.
- For k = 1, . . . , d, iterate until |w
(t+1)
k − w
(t)
k | < :
w
(t+1)
k ← w
(t)
k + η
n∑
i=1
x
(i)
j
[
y
(i) − ˆP (y
(i) = 1 | x
(i), w
(t))
]
.
19

---

## Page 21

# Chapter 5
# Naive Bayes Classifier
## 5.1 Gaussian Bayes
Recall that the Bayes decision rule (2.1) is the optimal classifier, but requires having knowledge
of P (Y | X) = P (X | Y )P (Y ), which is difficult to compute. To tackle this problem, we consider
appropriate models for the two terms: class probability P (Y ) and class conditional distribution
of features P (X | Y ).
Consider an example of X being continuous 1-dimensional and Y being binary. The class
probability P (Y ) then follows a Bernoulli distribution with parameter θ, i.e., P (Y = 1) = θ.
We further assume the Gaussian class conditional density
P (X = x | Y = i) =
1
√
2πσ2
y
exp
(
−
(x − μi)2
2σ2
i
)
, (5.1)
where we note that the distribution would be different for each class (hence the notation μi, σi).
In total there are 5 parameters: θ, μ0, μ1, σ0, σ1.
In case X is 2-dimensional, we would have
P (X = x | Y = i) =
1
√
2π|Σi|
exp
(
−
(x − μi)T Σ
−1
i (x − μi)
2
)
, (5.2)
where Σi is a 2 × 2 covariance matrix. In total there are 11 parameters: θ, μ0, μ1 (2-dimensional),
Σ0, Σ1 (2 × 2 symmetric matrix).
Further note that the decision boundary in this case is
P (Y = 1 | X = x)
P (Y = 0 | X = x)
=
P (X = x | Y = 1)P (Y = 1)
P (X = x | Y = 0)P (Y = 0)
=
√
|Σ0|
|Σ1|
exp
(
−
(x − μ1)T Σ
−1
1 (x − μ1)
2
+
(x − μ0)T Σ
−1
0 (x − μ0)
2
)
·
θ
1 − θ
. (5.3)
This implies a quadratic equation in x, but if Σ1 = Σ0 the quadratic terms cancel out and the
equation is linear.
The number of parameters we would need to learn for Gaussian Bayes in the general case, with
k labels and d-dimensional inputs, is:
- P (Y = i) = pi for 1 ≤ i ≤ k − 1: k − 1 parameters, and
20

---

## Page 22

- P (X = x | Y = i) ∼ N (μi, Σi): d parameters for μi and
d(d+1)
2 parameters for Σi,
which result in kd +
kd(d+1)
2 = O(kd2) parameters.
If X is discrete, again with k labels and d-dimensional inputs, the number of parameters is:
- P (Y = i) = pi for 1 ≤ i ≤ k − 1: k − 1 parameters, and
- P (X = x | Y = i) comes from a probability table with 2d − 1 entries,
which result is k(2d − 1) parameters to learn.
Having too many parameters means we need a lot of training data to learn them. We therefore
introduce an assumption that can significantly reduce the number of parameters.
## 5.2 Naive Bayes Classifier
Definition 6: (Naive Bayes Classifier)
The Naive Bayes Classifier is the Bayes decision rule with an additional “naive” assumption
that features are independent given the class label:
P (X | Y ) = P (X1, X2, . . . , Xd | Y ) =
d∏
i=1
P (Xi | Y ). (5.4)
In this case, the output class of an input x is
ˆfN B (x) = arg max
y
P (x1, . . . , xd | y)P (y) = arg max
y
d∏
i=1
P (xi | y)P (y).
Therefore, if the conditional assumption holds, Naive Bayes is the optimal classifier. Using this
assumption, we can then formulate the Naive Bayes classifier algorithm, where the class priors
and class conditional probabilities are estimated using MLE.
Algorithm 9: (Naive Bayes Classifier for discrete features)
Given training data {(x(i), y(i))}n
i=1 where x(i) = (x
(i)
1 , x
(i)
2 , . . . , x
(i)
d ), we compute the follow-
ings:
- Class prior: ˆP (Y = y) =
1
n
∑n
i=1 I
(
y(i) = y
)
.
- Class joint distribution:
ˆP (Xj = xj , Y = y) =
1
n
n∑
i=1
I
(
x
(i)
j = xj , y
(i) = y
)
.
- Prediction for test data given input x:
ˆfN B (x) = arg max
y
ˆP (y)
d∏
j=1
ˆP (xj , y)
ˆP (y)
= arg max
y
∑n
i=1 I
(
x
(i)
j = xj , y(i) = y
)
∑n
i=1 I (y(i) = y)
. (5.5)
21

---

## Page 23

Algorithm 10: (Naive Bayes Classifier for continuous features)
Given training data {(xi, yi)}n
i=1 where x(i) = (x
(i)
1 , x
(i)
2 , . . . , x
(i)
d ), we compute the followings:
- Class prior: ˆP (Y = y) =
1
n
∑n
i=1 I
(
y(i) = y
)
.
- Class conditional distribution:
ˆμjy =
1
∑n
i=1 I (y(i) = y)
n∑
i=1
x
(i)
j I
(
y
(i) = y
)
,
ˆσ
2
jy =
1
∑n
i=1 I (y(i) = y) − 1
n∑
i=1
(x
(i)
j − ˆμjy)
2I
(
y
(i) = y
)
,
ˆP (Xj = xj | Y = y) =
1
ˆσ2
jy
√
2π
exp
(
−
(x − ˆμjy)2
2ˆσ2
jy
)
.
- Prediction for test data given input x:
ˆfN B (x) = arg max
y
ˆP (y)
d∏
j=1
P (xj | y). (5.6)
As we noted earlier, the number of parameters in the above algorithms is much fewer.
Diving in the Math 8 - Number of parameters in Naive Bayes
Consider input variable X with discrete features X1, . . . , Xd each taking one of K values
and output label Y taking one of M values. Further suppose that the label distribution is
Bernoulli and the feature distribution conditioned on the label is multinomial.
Without naive Bayes assumption:
- M − 1 parameters p0, p1, . . . , pM −2 for label:
P (Y = y) =



py if y < M − 1
1 −
M −2∑
i=0
pi if y = M − 1
- For each label y, the corresponding probability table has K n − 1 parameters.
So the total number of parameters is M − 1 + M (K
n − 1) = M · K
n − 1 .
With naive Bayes assumption:
- M − 1 parameters p0, p1, . . . , pM −2 for labels, as mentioned above.
- For each Y = y and 1 ≤ i ≤ n, Xi | Y comes from a categorial distribution so it has
K − 1 parameters. So we need M n(K − 1) parameters for
{P (Xi = xi | Y = y) | i = 1..n, xi = 1..K, y = 0..M − 1}.
The total number of parameters is M − 1 + M n(K − 1) . Therefore the number of param-
eters is reduced from exponential to linear with the Naive Bayes assumption.
22

---

## Page 24

We note two important issues in Naive Bayes. First, the conditional independence assumption
does not always hold; nevertheless, this is still the most used classifier, especially when data
is limited. Second, in practice we typically use MAP estimates for the probabilities instead of
MLE since insufficient data may cause MLE to be zero. For instance, if we never see a training
instance where X1 = a and Y = b then, based on MLE, ˆP (X1 = a | Y = b) = 0. Consequently,
no matter what the values X2, . . . , Xd take, we see that
ˆP (X1 = a, X2, . . . , Xd | Y ) = ˆP (X1 = a | Y )
d∏
j=2
ˆP (Xj | Y ) = 0.
To resolve this issue, we can use a technique called smoothing and add m “virtual” data points.
Algorithm 11: (Naive Bayes Classifier for discrete features with smoothing)
Given training data {(xi, yi)}n
i=1 where x(i) = (x
(i)
1 , x
(i)
2 , . . . , x
(i)
d ), assume some prior dis-
tributions (typically uniform) Q(Y = b) and Q(Xj = a, Y = b). We then compute the
followings:
- Class prior: ˆP (Y = y) =
1
n
∑n
i=1 I
(
y(i) = y
)
.
- Class conditional distribution:
ˆP (Xj = xj | Y = y) =
∑n
i=1 I
(
x
(i)
j = xj , y(i) = y
)
+ mQ(Xj = xj , Y = y)
∑n
i=1 I (y(i) = y) + mQ(Y = y)
.
- Prediction for test data given input x:
ˆfN B (x) = arg max
y
ˆP (y)
d∏
j=1
P (xj | y). (5.7)
## 5.3 Text classification: bag of words model
We present a case study of Naive Bayes Classifier: text classification. Given the input text as
a string of words, we have to predict a category for it (i.e., what is the topic, is this a spam
email). Using the bag of words approach, we construct the input features X as the count of
how many times each word appears in the document. The dimension d of X is then the number
of distinct words in the document, which can be very large, leading to a huge probability table
for P (X | Y ) (with 2d − 1 entries). However, under the Naive Bayes assumption, P (X | Y ) is
simply a product of probability of each word raised to its count. It follows that
ˆfN B (x) = arg max
y
P (y)
wk∏
w=w1
P (w | Y )
count(w), (5.8)
where w1, . . . , wk are all the distinct words in the document. Note that here we assume the order
of words in the document doesn’t matter, which sounds silly but often works very well.
## 5.4 Generative vs Discriminative Classifer
We first note the following comparison between Naive Bayes and Logistic Regression:
23

---

## Page 25

In other words, the two methods have representation equivalence - in particular, a linear decision
boundary. However, keep in mind that:
- This is only true in the special case where we assume the feature variances are independent
of class label (more specifically, Σ1 = Σ0 in (5.3)).
- Logistic regression is a discriminative model and makes no assumption about P (X | Y ) in
learning. Instead, it assumes a sigmoid form for P (Y | X).
- The two optimize different functions: MLE / MCLE vs MAP / MCAP and yield different
solutions.
More generally, we outline the problem between a generative classifier (e.g., Naive Bayes) and a
discriminative classifier (e.g., logistic regression).
Generative Discriminatve
Assume some prorability model for P (Y ) and
P (X | Y ).
Assume some functional form for P (Y | X)
or the decision boundary.
Estimate parameters of probability models
from training data.
Estimate parameters of functional form di-
rectly from training data.
Table 5.1: Generative (model-based) vs Discriminative (model-free) classifier.
24

---

## Page 26

# Chapter 6
# Neural Networks and Deep Learning
## 6.1 Definition
Definition 7: (Neural network)
Given a function f : X → Y such that:
- f can be non-linear
- X is vector of continuous / discrete variables
- Y is vector of continuous / discrete variables
A neural network is a way to represent f by a network of logistic / sigmoid unit.
In its simplest form, a neural network has one input node and one output node
x o
w
so it is equivalent to logistic regression
o(x) = σ(wx) =
1
1 + e−wx . (6.1)
On the other hand, a neural network with one hidden layer
x oh o
w0 wh
25

---

## Page 27

would output
o(x) = σ(w0 +
∑
h
wh σ(w
h
0 +
∑
i
w
h
i xi)
︸ ︷︷ ︸
oh
). (6.2)
More generally, prediction in neural networks is done by starting from the input layer and, for
each subsequent layer, computing the output of the sigmoid units (forward propagation).
## 6.2 Training a neural network
## 6.2.1 Gradient descent
Let’s treat a neural network as a function Y = fw(X) +  where fw is determined given w and
 ∼ N (0, σ2I), so Y ∼ N (fw(X), σ2I). One way to learn the weights is by MCLE:
̂wM CLE = arg max
w
ln
(
∏
l
P (y
(l) | x
(l), w)
)
= arg min
w
∑
l
(y
(l) − ̂ fw(x
(l)))
2.
In other words, the weights are trained to minimize sum of squared errors of predicted network
outputs. We may also want to restrict the weights to small values, and this bias can be encoded
in MCAP:
̂wM CAP = arg max
w
ln
(
P (w)
∏
l
P (y
(l) | x
(l), w)
)
= arg min
w
c
∑
i
w
2
i +
∑
l
(y
(l) − ̂ fw(x
(l)))
2,
where P (w) ∝ exp(−wT w/2τ 2) (recall the connection between Ridge Regression and MCAP
(3.10)). In other words, the weights are trained to minimize sum of squared errors of predicted
network outputs plus weight magnitudes.
To perform the above optiminization, we introduce a routine called gradient descent.
Algorithm 12: (Gradient descent algorithm)
Initialize: Pick w at random.
Gradient:
∇wE(w) =
(
∂E(w)
∂w0
,
∂E(w)
∂w1
, . . . ,
∂E(w)
∂wd
)
.
Update:
∆w = −η∇wE(w)
w
(t+1)
t ← w
(t)
i − η
∂E(w)
∂wi
,
where η > 0 is the learning rate.
Suppose we feed the training data {(x(l), y(l))}n
l=1 where x(l) is d-dimensional into a one-layer
neural network with d input nodes xi and one output node o. The gradient descent w.r.t every
26

---

## Page 28

output weight wi is
∂E
∂wi
=
n∑
l=1
(o
(l) − y
(l))o
(l)(1 − o
(l))x
(l)
i . (6.3)
Diving in the Math 9 - Gradient descent for weights at output layer
x1
x2
. . .
xd
∑
σ o
w1
w2
wd
net =
∑d
i=1 wixi o = σ(net) =
1
1+e−net
Note that σ(x) =
1
1+e−x is the sigmoid function and
d
dx σ(x) = σ(x)(1 − σ(x)).
We have E(w) =
1
2
∑n
l=1(y(l) − o(l))2 so
∂E
∂wi
=
1
2
n∑
l=1
∂
∂wi
(y
(l) − o
(l))
2 =
1
2
n∑
l=1
∂(y(l) − o(l))2
∂o(l) ·
∂o(l)
∂wi
=
n∑
l=1
(o
(l) − y
(l)) ·
∂o(l)
∂wi
.
Now note that
∂o(l)
∂wi
=
∂o(l)
∂net(l) ·
∂net(l)
∂wi
= o
(l)(1 − o
(l))x
(l)
i ,
so
∂E
∂wi
=
n∑
l=1
(o
(l) − y
(l))o
(l)(1 − o
(l))x
(l)
i .
For the hidden layers, consider
∂E
∂whk where whk connects a node oh from layer L to ok from layer
L + 1. Further assume that Γ is the set of all nodes at layer L + 2. We then have the expression
∂E
∂whk
= ohok(1 − ok)
∑
γ∈Γ
δγ wkγ., (6.4)
where δγ = oγ (1 − oγ )
∂E
∂oγ . This means that we can first compute the gradients w.r.t the weights
at the output layer, then propagate back to the weights at one previous layer, then two previous
layers, and so on, until the input layer.
27

---

## Page 29

Diving in the Math 10 - Gradient descent for weights at hidden layers
We would like to evaluate
∂E
∂whk
=
∂E
∂ok
·
∂ok
∂whk
.
Since
∂ok
∂whk = ok(1 − ok)oh, we can rewrite the above expression as
∂E
∂whk
= ohok(1 − ok)
∂E
∂ok
= ohδk.
Now we consider
∂E
∂ok
=
∑
γ
∂E
∂oγ
·
∂oγ
∂ok
=
∑
γ
∂E
∂oγ
oγ (1 − oγ )wkγ =
∑
γ
δγ wkγ .
Hence
∂E
∂whk
= ohok(1 − ok)
∑
γ
δγ wkγ.
## 6.2.2 Backpropagation
More generally, we can derive the backpropagation algorithm as in the next page. We also note
the special properties of this algorithm:
- It computes gradient descent over the entire network weight vector. Training can take
thousands of iterations, which is slow, but using network after training is very fast.
- It can easy generalize to arbitrary directed graphs.
- It will find a local, not necessarily global error minimum (because error function E is no
longer convex in weights), but often works well in practice.
- It often includes a weight momentum α:
∆w
(n)
ij = ηδj xij + α∆w
(n−1)
ij .
The expressive capabilities of neural network are powerful:
- Every boolean function can be represented by a network with one hidden layer, but may
require exponential (in number of inputs) hidden units.
- Every bounded continuous function can be approximated with arbitrarily small error, by
a network with one hidden layer.
- Any function can be approximated to arbitrary accuracy by a network with two hidden
layers.
However, neural network may still encounter the issue of overfitting, which can be avoided by
MCAP, early stopping, or by regulating the number of hidden units, which essentially prevents
overly complex models.
28

---

## Page 30

Algorithm 13: (Backpropagation)
Denote the followings:
- l is the index of the traning example
- yk is target output (label) of output unit k
- oh, ok are unit output (obtained by forward propagation) of output units h, k. If i is
input variable, oi = xi.
- wij is the weight from node i to node j in the next layer.
Initialize all weights to small random numbers. Until satisfied, do
- For each training example, do
1. Input the training example to the network and compute the network outputs,
using forward propagation.
2. For each output unit k, let
δ
(l)
k ← o
(l)
k (1 − o
(l)
k )(y
(l)
k − o
(l)
k ).
3. For each hidden unit h, let
δ
(l)
h ← o
(l)
h (1 − o
(l)
h )
∑
k∈K
whkδ
(l)
k ,
where K is the set of output nodes.
4. Update each network weight wij :
wij ← wij + ∆w
(l)
ik
where ∆w
(l)
ij = −ηδ
(l)
j o
(l)
i .
Unlike in logistic regression, the function E(w) in neural network is not convex in w. Thus,
gradient descent (and backpropagation) will find a local, not necessarily global minimum, but
it often works well in practice.
Finally, we note the two ways in which backpropagation can be implemented in practice: Batch
mode and Incremental mode (also called Stochastic Gradient Descent). Incremental mode is
faster to compute and can approximate Batch mode arbitrary closely if η is small enough.
Batch mode Gradient mode
Let ED(w) =
1
2
∑
l∈D(y(l) − o(l))2. Let El(w) =
1
2 (y(l) − o(l))2.
Do until satisfied:
1. Compute the gradient ∇ED(w).
2. w ← w − η∇ED(w).
Do until satisfied:
- For each training example l in D:
1. Compute the gradient ∇El(w).
2. w ← w − η∇El(w).
Table 6.1: Batch mode vs Gradient mode
29

---

## Page 31

## 6.3 Convolutional neural networks
Definition 8: (Deep architectures)
Deep architectures are composed of multiple levels of non-linear operations, such as neural
nets with many hidden layers.
Deep learning methods aim at learning feature hierarchies, where features from the higher levels
of the hierarchy are formed by lower level features. One such method is convoluational neural
network, which, compared to standard feedforward neural network:
- have much fewer connections and parameters
- is easier to train
- has only slightly worse theoretically best performance.
First, we define the term convolution.
Definition 9: (Convolution)
The convolution of two functions f and g, denoted f ∗ g, is defined as:
- If f and g are continuous:
(f ∗ g)(t) =
∫ ∞
−∞
f (τ )g(t − τ )dτ =
∫ ∞
−∞
f (t − τ )g(τ )dτ. (6.5)
- If f and g are discrete:
(f ∗ g)[n] =
∞∑
m=−∞
f [m]g[n − m] =
∞∑
m=−∞
f [n − m]g[m]. (6.6)
- If discrete g has support on {−M, . . . , M }:
(f ∗ g)[n] =
M∑
m=−M
f [n − m]g[m]. (6.7)
Informally, the convolution gives a sense of how much two functions “overlap.” A simple con-
volutional neural network (CNN) is a sequence of layers, each of which transforms one volume
of activations to another through a differentiable function. We use three main types of layers to
build the network architectures: Convolutional Layer, Pooling Layer, and Fully Connected Layer
30

---

## Page 32

(exactly as seen in regular Neural Networks). Typically, CNNS are used for image classification
in computer vision.
We now discuss the components of a CNN. The following text excerpts are from Chapter 10 of
Artificial Intelligence for Humans, Vol 3: Neural Networks and Deep Learning and Stanford’s
CS 231n.
## 6.3.1 Convolutional Layer
The primary purpose of a convolutional layer is to detect features such as edges, lines, blobs of
color, and other visual elements. Each feature is represented by a filter; the more filters that we
give to a convolutional layer, the more features it can detect.
More formally, a filter is a square 2D matrix that scans over the image. The convolutional layer,
which is essentially a set of filters, acts as a smaller grid that sweeps left to right over each of
row of the image. Each cell in a filter is a weight.
The sweeping phase (forward propagation) is done as follows. First, the input image may be
padded with some layers of zero cells as need. The stride specifies the number of positions at
which the convolutional filters will stop. The convolutional filters move to the right, advancing
by the number of cells specified in the stride. Once the far right is reached, the convolutional
filter moves back to the far left, then it moves down by the stride amount and continues to the
right again. Hence, the number of steps in one sweeping phase is
Number of steps =
W − F + 2P
S
+ 1,
where W is the image size, F is the filter size, P is the padding and S is the stride.
We can use the same set of weights as the convolutional filter sweeps over the image. This
process allows convolutional layers to share weights and greatly reduce the amount of processing
needed. In this way, we can recognize the image in shift positions because the same convolutional
filter sweeps across the entire image.
The input and output of a convolutional layer are both 3D boxes. For the input to a convolu-
tional layer, the width and height of the box is equal to the width and height of the input image.
The depth of the box is equal to the color depth of the image. For an RGB image, the depth
is 3, equal to the components of red, green, and blue. If the input to the convolutional layer
is another layer, then it will also be a 3D box; however, the dimensions of that 3D box will be
dictated by the hyper-parameters of that layer. Like any other layer in the neural network, the
size of the 3D box output by a convolutional layer is dictated by the hyper-parameters of the
layer. The width and height of this box are both equal to the filter size. However, the depth is
equal to the number of filters.
A visualization for the sweeping phase is in the Convolution Demo section at Stanford’s CS
231n. In summary, the procedure taking place at the convolutional layer is as follows.
31

---

## Page 33

Algorithm 14: (Convolutional layer’s forward pass)
Accepts a 3D image of size W1 × H1 × D1.
Requires four hyperpameters: number of filters K, spatial extent F , stride S, and amount
of zero padding P .
Produces a 3D image of size W2 × H2 × D2 where
W2 =
W1 − F + 2P
S
+ 1; H2 =
H1 − F + 2P
S
+ 1; D2 = K. (6.8)
With parameter sharing, it introduces F × F × D1 weights per filter, for a total of F × F ×
D1 × K weights and K biases. In the output volume, the d-th depth slice (of size W2 × H2)
is the result of performing a valid convolution of the d-th filter over the input volume with
a stride of S, and then offset by d-th bias.
## 6.3.2 Pooling layer
Pooling layer downsamples an input 3D image to a new one with smaller widths and heights.
Typically a pooling layer follows immediately after a convolutional layer. A typical choice for
pooling is max-pooling, which, for every f × f region in the input image, outputs the maximum
number in that region to the output image.
Algorithm 15: (Pooling layer’s forward pass)
Accepts a volume of size W1 × H1 × D1.
Requires two hyperparameters: spatial extent F and stride S, Produces a volume of size
W2 × H2 × D2 where:
W2 =
W1 − F
S
+ 1; H2 =
H1 − F
S
+ 1; D2 = D1. (6.9)
Introduces zero parameters since it computes a fixed function of the input. For Pooling
layers, it is not common to pad the input using zero-padding.
It is worth noting that there are only two commonly seen variations of the max pooling layer
found in practice: A pooling layer with F = 3, S = 2 (also called overlapping pooling), and more
commonly F = 2, S = 2.
## 6.3.3 Fully Connected Layer
This is the same layer from a feedforward neural network, with two hyperparameters: neuron
count and activation function. Every neuron in the the previous layer’s 3D image output is
connected to each neuron in this layer through a weight value. A dot product of the input
(flattened to 1D) and the weight vector is then passed to the activation function. Dense layers
can employ many different kinds of activation functions, such as ReLU, sigmoid or tanh.
32

---

## Page 34

# Chapter 7
# Support Vector Machine
## 7.1 Introduction
Recall that a regression classifier with linear decision boundary would typically look like
where the boundary is determined by taking into account all data points (e.g., linear regression
(3.1)). In this case, the decision line is closer to the blue nodes since many of them are far
off to the right. However, note that there could be many possible classifiers that have different
boundaries but yield the same outcome:
One way to decide on a single classifier is to find a max margin classifier: a boundary that leads
to the largest margin from both sets of points. This also means that instead of fitting all points,
33

---

## Page 35

we may consider only the “boundary” points, and we want to learn a boundary that leads to the
largest margin from points on both sides. These boundary points are called the support vectors.
In particular, we would specify a max margin classifier based on parameters w and b, and then
perform classification as follows
## 7.2 Primal form
## 7.2.1 Linearly separable case
Our goal, as previously mentioned, is to find the maximum margin. Let’s define the width of
the margin by M , we can then see that
M =
2
√
wT w
. (7.1)
34

---

## Page 36

Diving in the Math 11 - Computing margin M in terms of weight w and bias b
First observe that the vector w is orthogonal to the +1 plane. To prove this, let u and v be
any two points on the +1 plane then
w
T u = w
T v = 1 − b ⇒ w
T (u − v) = 0.
Similarly, w is orthogonal to the −1 plane too. Hence, if x+ is a point on the + plane and
x− is the point closest to x+ on the − plane, then the vector from x+ to x− is parallel to w.
In other words, x+ = λw + x− for some λ. Now we have
w
T x
+ + b = 1
w
T (λw + x
−) + b = 1
w
T x
− + λw
T w = 1
λ =
2
wT w
.
Hence
M = |x
+ − x
−| = |λw| = λ
√
wT w =
2
wT w
√
wT w =
2
√
wT w
.
We can now search for the optimal parameters by finding a solution that:
1. Correctly classifies all points
2. Maximizes the margin (or equivalently minimizes wT w).
Several optimization methods can be used: Gradient descent, simulated annealing, EM, etc. In
this case, the problem also belongs to the category of quadratic programming (QP).
Definition 10: (Quadratic programming)
Quadratic programming solves the optimization problem
min
u
uT Ru
2
+ d
T u + c,
where u is a vector, R is square matrix, d is vector and c is scalar.
Furthermore, u is subject to n inequality constraint
ai1u1 + ai2u2 + . . . ≤ bi, 1 ≤ i ≤ n,
and k equivalency constraint
aj1u1 + aj2u2 + . . . = bn+j , 1 ≤ j ≤ k.
More specifically, we can frame the margin maximization problem as a QP problem:
min
w
wT w
2
subject to n constraints if there are n samples x.
- wT x + b ≥ 1 for all x in class +1,
- wT x − b ≤ −1 for all x in class −1,
35

---

## Page 37

## 7.2.2 Non linearly separable case
So far we have assumed that the data is linearly separable, i.e., there is a line wT x + b that
perfectly separates the +1 and −1 class. But this is usually not the case in practice, as there
can be noise and outliers. One way to address this is to penalize the number of misclassified
points m, i.e.,
min
w
w
T w + C · m,
where C is a regularization constant. However, this is hard to encode in a QP problem.
Instead of minimizing the number of misclassified points we can minimize the distance between
these points and their correct plane. In this case, the new optimization problem is
min
w
wT w
2
+ C
n∑
i=1
i,
subject to 2n constraints if there are n samples x(i):
- wT x(i) + b ≥ 1 − i for all x(i) in class +1
- wT x(i) + b ≤ −1 + i for all x(i) in class −1.
- i ≥ 0 for all i.
In summary, we have two optimization problems for two cases:
Separable case Non-separable case
Find
min
w
wT w
2
subject to
- wT x + b ≥ 1 for all x
in class +1
- wT x + b ≤ −1 for all
x in class −1
Find
min
w
wT w
2
+ C
n∑
i=1
i
subject to
- wT x + b ≥ 1 − i for all
xi in class +1
- wT x + b ≤ −1 + i for
all xi in class −1
- i ≥ 0 for all i.
Table 7.1: Optimization constraints for separable and non-separable case in primal SVM
## 7.3 Dual representation
## 7.3.1 Linearly separable case
Instead of solving the QPs in Table 7.1 directly, we will solve a dual formulation of the SVM
optimization problem. The main reason for switching to this type of representation is that it
would allow us to use a neat trick that will make our lives easier (and the run time faster).
Starting from the separable case, note that we can rephrase the constraints as
(w
T x
(i) + b)y
(i) ≥ 1 (7.2)
for all i, where yi - the class of xi - is ±1. We can then encoding this as part of our minimization
problem using Lagrange multiplier.
36

---

## Page 38

Algorithm 16: (Lagrange multiplier method)
Consider a problem of finding
min
w
f (w)
such that hi(w) = 0, i = 1, . . . , l
In the Lagrange multiplier method, we can define the Lagrangian to be
L(w, β) = f (w) +
l∑
i=1
βihi(w),
where the βi’s are called the Lagrange multipliers. We would then find and set L’s partial
derivatives to zero:
∂L
∂wi
= 0;
∂L
∂βi
= 0,
and solve for w and β.
More generally, consider the following primal optimization problem:
min
w
f (w)
such that gi(w) ≤ 0, i = 1, . . . , k
hi(w) = 0, i = 1, . . . , l
To solve it, we start by defining the generalized Lagrangian:
L(w, α, β) = f (w) +
k∑
i=1
αigi(w) +
l∑
i=1
βihi(w)
where the αi, βi’s are the Lagrange multipliers.
Using the Lagrange multiplier, consider the quantity
θp(w) = max
α,β:αi≥0
L(w, α, β)
then our minimization problem becomes
min
w
θp(w) = min
w
max
α,β:αi≥0
L(w, α, β).
Specifically, our original problem is
min
w
wT w
2
such that gi(w) = −y
(i)(w
T x
(i) + b) + 1 ≤ 0.
which can be translated to
min
w
max
α
wT w
2
−
∑
i
αi(y
(i)(w
T x
(i) + b) − 1)
︸ ︷︷ ︸
L(w,α)
(7.3)
37

---

## Page 39

where αi ≥ 0 for all i. Setting the derivative of L w.r.t w, α, b respectively we get:
0 =
∂L
∂w
= w −
n∑
i=1
αiy
(i)x
(i) ⇒ w =
n∑
i=1
αiy
(i)x
(i). (7.4)
0 =
∂L
∂αi
= −y
(i)(w
T x
(i) + b) − 1 ⇒ b = y
(i) − w
T x
(i) for i where αi > 0. (7.5)
0 =
∂L
∂b
=
n∑
i=1
αiy
(i). (7.6)
We mentioned earlier that the only data points of importance are the support vectors, which
affect the margin. Originally, we need to find the points that touch the boundary of the margin
(i.e., wT x + b = ±1). In this case, howerver, (7.4) gives us the support vectors directly, which
are the points (x(i), y(i)) where αi > 0.
Substituting the above results back into (7.3), we get the equivalent problem of
max
α
∑
i
αi −
1
2
∑
i,j
αiαiy
(i)y
(j)(x
(i))
T x
(j) (7.7)
where
∑
i αiy(i) = 0 and αi ≥ 0 for all i. After solving for α in this new problem, to evaluate a
new sample x, we simply compute
ˆy = sign(w
T x + b) = sign
(
∑
i
αiyi(x
(i))
T x + b
)
. (7.8)
Note that both the optimization function (7.7) and decision function (7.8) rely on the sum of
dot products (x(j))T x(i), which can be expensive to compute.
## 7.3.2 Transformation of inputs
When the data is not linearly separable, the original input space (x) can be mapped to some
higher-dimensional feature space (φ(x)) where the training set is separable.
For instance, we can map (x) → (x, x2) (from 1D to 2D) and (x1, x2) → (x2
1, x2
2,
√
2x1x2) (from
2D to 3D):
38

---

## Page 40

In general, if the data is mapped into sufficiently high dimension, then samples will be linearly
separable. n data points can be separable in a space of n − 1 dimensions or more. However, this
transformation poses two difficulties:
- High computation burden due to high-dimensionality.
- Many more parameters.
SVM solves these two issues by:
- Using dual formulation, which only assigns parameters to samples, not features (i.e., each
x(i) has an associated αi).
- Using kernel tricks for efficient computation.
39

---

## Page 41

Note that if we have n data points with m dimensions then the number of parameters is m in
primal form (i.e., the features of weight w) and n in dual form (i.e., an αi for each x(i)). At first
glance, because n  m, the primal formation is at an advantage. However, note that in dual
form we only care about the support vectors; in other words, the parameters are only those αi
that are positive, and their number is usually a lot less than n. Hence, the dual form is not worse
than primal form in the original space. In the transformed space, as x increases in dimension,
so does w, so the primal form requires more parameters, while the dual form generally also sees
an increase in the number of support vectors, but not as much.
## 7.3.3 Kernel tricks
While working in higher dimensions is beneficial, it also increases our run time because of the
dot product computation. However, there is a neat trick we can use.
Consider, for example, all quadratic terms for the features x1, x2, . . . , xm:
φ(x) = (1,
√
2x1, . . . ,
√
2xm︸ ︷︷ ︸
m+1 linear terms
, x
2
1, . . . , x
2
m︸ ︷︷ ︸
m quadratic terms
,
√
2x1x2, . . . ,
√
2xm−1xm︸ ︷︷ ︸
m(m−1)/2 pairwise terms
)
T . (7.9)
The dot product operation would normally be
φ(x)
T φ(z) =
∑
i
2xizi +
∑
i
(xi)
2(zi)
2 +
∑
i<j
2xixj zizj + 1,
which has O(m2) operations. However, we can obtain dramatic savings by noting that
(x · z + 1)
2 = (x · z)
2 + 2(x · z) + 1
= (
∑
i
xizi)
2 +
∑
i
2xizi + 1
=
∑
i
2xizi +
∑
i
(xi)
2(zi)
2 +
∑
i<j
2xixj zizj + 1
= φ(x)
T φ(z).
In other words, to compute φ(x)T φ(z), we can simply compute x · z + 1 (which only needs m
operations) and then square it. Hence, we don’t need to work directly with the transformations
φ(x) to compute their dot products. The function φ in this case (7.9) is called a polynomial
kernel (of degree 2).
The kernel trick works for higher order polynomials as well. In general, a polynomial of degree
d can be computed by (x · z + 1)d. Beyond polynomials there are other very high dimensional
basis functions that can be made practical by finding the right kernel function, such as Radial
basis kernel function K(x, z) = exp
(
−
(x−z)2
2σ2
)
.
40

---

## Page 42

## 7.3.4 Non linearly separable case
Using the Lagrange multiplier method on the optimization function for the primal form’s non
linearly separable case (Table 7.1), we obtain our dual target function
max
α
∑
i
αi −
1
2
∑
i,j
αiαj y
(i)y
(j)(x
(i))
T (x
(j)) (7.10)
subject to
∑
i αiy(i) = 0 and C > αi ≥ 0 (so now the αi’s are bounded above by the regularization
constant). To evaluate a new sample x, we similarly perform the computation as in (7.8).
In summary, we have two optimization problems for two cases:
Separable case Non-separable case
Find
max
α
∑
i
αi −
1
2
∑
i,j
αiαiy
(i)y
(j)(x
(i))
T x
(j)
where
∑
i αiy(i) = 0 and αi ≥ 0 for all i.
Find
max
α
∑
i
αi −
1
2
∑
i,j
αiαiy
(i)y
(j)(x
(i))
T x
(j)
where
∑
i αiy(i) = 0 and C > αi ≥ 0 for all i.
Table 7.2: Optimization constraints for separable and non-separable case in dual SVM.
## 7.4 Other topics
## 7.4.1 Why do SVMs work?
If we are using huge features spaces (with kernels) why are we not overfitting the data?
- Number of parameters remains the same (and most are set to 0).
- While we have a lot of input values, at the end we only care about the support vectors
and these are usually a small group of samples.
- The minimization (or the maximizing of the margin) function acts as a sort of regularization
term leading to reduced overfitting.
## 7.4.2 Multi-class classification with SVM
If we have data from more than two classes, most common solution is the one-versus-all approach:
- Create a classifer for each class against all other data.
- For a new point use all classifiers and compare the margin for all selected classes. The
class with the largest margin is selected.
Note that this is not necessarily valid since this is not what we trained the SVM for, but often
works well in practice.
41

---

## Page 43

# Chapter 8
# Ensemble Methods and Boosting
## 8.1 Introduction
Consider the simple (weak) learners (e.g., naive Bayes, logistic regression, decision tree) - those
that don’t learn too well but still better than chance, i.e. error < 50% but not close to 0. They
are good (low variance, usually don’t overfit) but also bad (high bias, can’t solve hard problems).
Can we somehow improve them by combining them together? A simple approach is “bucket of
models”:
- Input:
– Your top T favorite learners L1, . . . , LT
– A dataset D
- Learning algorithm:
1. Use 10-fold cross validation to estimate the error of L1, . . . , LT
2. Pick the best (lowest 10-CV error) learner L∗
3. Train L∗ on D and return its hypothesis h∗
This approach is simple and will give results not much worse than the best of the “base learners”,
but what if there’s not a single best learner? How do we come up with a method that combines
multiple classifiers? One way is to perform voting (ensemble methods):
- Instead of learning a single (weak) classifier, learn many weak classifiers that are good at
different parts of the input space.
- Output class: (Weighted) vote of each classifier
– Classifiers that are most “sure” will vote with more conviction
– Each classifier will be most “sure” about a particular part of the space
– On average, do better than single classifier!
The question, then, is how we can force classifiers to learn about different parts of the input
space and weigh the votes of different classifiers? This leads us to the idea of boosting :
- Idea: given a weak learner, run it multiple times on (reweighted ) training data, then let
the learned classifiers vote.
- On each iteration t:
42

---

## Page 44

– weigh each training example by how incorrectly it was classified
– learn a hypothesis ht and its strength αt
- Final classifier: a linear combination of the votes of the different classifiers weighted by
their strength
Note the notion of a weighted dataset - in particular, if D(i) be the weight of the i-th training
example (x(i), y(i)), then it counts as D(i) examples. From now, in all calculations, whenever
used, the i-th training example counts as D(i) “examples”.
With this in mind, we can now define the full boosting algorithm (Shapire, 1998):
Algorithm 17: (AdaBoost)
Given dataset {(x(1), y(1)), . . . , (x(m), y(m))} where x(i) ∈ X, y(i) ∈ Y = {±1}.
Initialize D1(i) =
1
m .
For t = 1, . . . , T :
- Train weak learner using distribution Dt.
- Get weak classifier ht : X → R.
- Compute the error t =
∑m
i=1 Dt(t)I
(
ht(x(i)) 6 = y(i))
and strength αt =
1
2 ln
(
1−t
t
)
.
- Update
Dt+1(i) =
Dt(i) exp(−αty(i)ht(x(i))
Zt
where
Zt =
m∑
i=1
Dt(i) exp(−αty
(i)ht(x
(i)))
is a normalization factor (chosen so that
∑m
i=1 Dt+1(i) = 1).
Output the final classifier H(x) = sign
(
T∑
t=1
αtht(x)
)
.
An example is shown below.
43

---

## Page 45

44

---

## Page 46

## 8.2 Mathematical details
We now examine at each of the above formulas to see how they were derived. First observe that:
- t is the fraction of misclassified (weighted) samples in iteration t. Recall our earlier
definition of a weak learner as one that has error < 50%. Hence we always have t < 0.5
and therefore αt =
1
2 ln
(
1−t
t
)
> 0.
- If sample i is classified correctly then y(i)ht(x(i)) = 1 so
Dt(i) exp(−αty
(i)ht(x
(i))) =
Dt(i)
exp(αi)
< Dt(i),
i.e., the weight of this sample decreases. On the other hand, if sample i is classified
incorrectly, then its weight increases.
In other words, in each iteration the classifier will focus on a different set of points (more
specifically, those that were misclassified in the previous iteration), and in the end, we hope that
the combination of these classifiers (over all iterations) can classify all points correctly. This is
the idea behind boosting. Now, to prove that it does work (i.e., the error converges to 0 after
some number of iterations), we answer the following questions.
## 8.2.1 What αt to choose for hypothesis ht?
Note that the training error of the final classifier H is bounded by
1
m
m∑
i=1
I
(
H(x
(i)) 6 = y
(i))
≤
1
m
m∑
i=1
exp(−y
(i)f (x
(i))) =
T∏
t=1
Zt (8.1)
where f (x) =
∑T
t=1 αtht(x) and H(x) = sign (f (x)).
45

---

## Page 47

Diving in the Math 12 - Upper bound of final classifier’s training error
To prove the first inequality, note that:
- Each correctly classified sample i contributes 0 to the LHS and
1
me to the RHS.
- Each incorrectly classified sample i contributes
1
m to the LHS and
e
m to the RHS.
In other words, I
(
H(x(i)) 6 = y(i))
< exp(−y(i)f (x(i))) for all i, so
∑
i I
(
H(x(i)) 6 = y(i))
<∑
i exp(−y(i)f (x(i))).
To prove the second inequality, note that the definition of Dt gives us
DT +1(i) = DT (i) ·
exp(−αT y(i)hT (x(i)))
ZT
= DT −1(i) ·
exp(−αT −1y(i)hT −1(x(i)))
ZT −1
·
exp(−αT y(i)hT (x(i)))
ZT
= . . .
=
exp(−
∑
t αty(i)ht(x(i)))
m
∏
t Zt
=
exp(−y(i)f (x(i)))
m
∏
t Zt
.
On the other hand, because we define the Zt’s as normalization factors,
1 =
m∑
i=1
DT +1(i) =
1
m
∏
t Zt
m∑
i=1
exp(−y
(i)ht(x
(i))),
which leads to
1
m
m∑
i=1
exp(−y
(i)f (x
(i))) =
T∏
t=1
Zt.
In other words, to guarantee low error, we just need to make sure its upper bound
∏
t Zt is small.
We can tighten this bound greedily by choosing αt on each iteration to minimize Zt.
To do so, let’s define the error at iteration t as t =
∑
i Dt(i)I
(
ht(x(i)) 6 = y(i))
.
It then follows that
Zt =
∑
t
Dt(i) exp(−αty
(i)ht(x
(i))) = (1 − t) exp(−αt) + t exp(αt).
We can then choose αt that minimizes Zt by solving
∂Zt
∂αt = 0, which yields αt =
1
2 ln
(
1−t
t
)
.
Further note that αt and t are negatively correlated, so intuitively αt is the “strength” of
classifier ht. Hence, we have shown how to minimize
∏
t Zt, but how small can this minimum
value be?
## 8.2.2 Show that training error converges to 0
We can further derive another upper bound for the training error:
err(H) =
1
m
m∑
i=1
I
(
H(x
(i)) 6 = y
(i))
≤
T∏
t=1
Zt ≤ exp
(
−2
∑
t
γ
2
t
)
(8.2)
where γt =
1
2 − t.
46

---

## Page 48

Diving in the Math 13 - Convergence of AdaBoost’s training error
Note that
αt =
1
2
ln
(
1 − t
t
)
⇒ exp(αt) =
√
1 − t
t
,
and also
t =
∑
y(i)6 =ht(x(i))
Dt(i); 1 − t =
∑
y(i)=ht(x(i))
Dt(i).
We now have
Zt =
∑
i
Dt(i) exp(−αty
(i)ht(x
(i)))
=
∑
y(i)6 =ht(x(i))
Dt(i) exp(−αty
(i)ht(x
(i))) +
∑
y(i)=ht(x(i))
Dt(i) exp(−αty
(i)ht(x
(i)))
=
∑
y(i)6 =ht(x(i))
Dt(i)
(√
1 − t
t
)−y(i)ht(x(i))
+
∑
y(i)=ht(x(i))
Dt(i)
(√
1 − t
t
)−y(i)ht(x(i))
=
∑
y(i)6 =ht(x(i))
Dt(i)
(√
1 − t
t
)
+
∑
y(i)=ht(x(i))
Dt(i)
(√
t
1 − t
)
=
√
1 − t
t
·


∑
y(i)6 =ht(x(i))
Dt(i)

 +
√
t
1 − t
·


∑
y(i)=ht(x(i))
Dt(i)


=
√
1 − t
t
· t +
√
t
1 − t
· (1 − t)
= 2
√
t(1 − t).
Furthermore, for any x ∈ R, 1 − x ≤ exp(−x). Substitute x = 4γ 2
t we see that
1 − 4γ
2
t ≤ exp(−4γ
2
t ) ⇒
√
1 − 4γ 2
t ≤ exp(−2γ
2
t ).
Now we have
Zt = 2
√
t(1 − t) =
√
1 − 4γ 2
t ≤ exp(−2γ
2
t ),
hence
err(H) ≤
T∏
t=1
Zt ≤
T∏
t=1
exp(−2γ
2
t ) = exp(−2
∑
t
γ
2
t ).
It then follows that, as the number of iterations T increases, exp(−2
∑T
t=1 γ 2
t ) decreases expo-
nentially, so the training error also approaches 0 exponentially fast.
47

---

## Page 49

In practice, this also happens quite quickly. In fact, Schapire (1989) showed that in digit recog-
nition, the testing error can still decrease even after the training error reaches 01. Boosting is
also robust to overfitting.
Some weak learners also have their own ensemble methods apart from AdaBoost. For example,
an ensemble of decision tree is called a random forest. For each tree we select a subset of
attributes (recommended subset size = square root of number of total attributes) and build the
tree using only the selected attributes. An input sample is the classified using majority voting.
1Note that the training error reported in this graph is the global training error where each input is weighed
equally as usual. During the iterations of AdaBoost, however, we are concerned with the weighted errors t. In
this case, while the global training error is 0, the t’s may still be > 0, so there is room for improvement, and
therefore the test error can still decrease.
48

---

## Page 50

# Chapter 9
# Principal Component Analysis
## 9.1 Introduction
Suppose we are given data points in d-dimensional space and want to project them into a
lower dimensional space while preserving as much information as possible (e.g., find best planar
approximation to 3D data or 104D data). In particular, choose an orthogonal projection that
minimizes the squared error in reconstructing original data.
Like auto-encoding neural networks, PCA learns re-representation of input data that can best
reconstruct it. However, PCA has some differences:
- The learned encoding is a linear function of inputs
- No local minimum problems when training
- Given d-dimensional data X, learns d-dimensional representation where:
– the dimensions are orthogonal
– The top k dimensions are the k-dimensional linear re-representation that minimizes
reconstruction error (sum of squared errors)
In particular, PCA involves orthogonal projection of the data onto a lower-dimensional linear
space that equivalently:
1. minimizes the mean squared distance between data points and projections
2. maximizes variance of projected data
PCA has the following properties:
- PCA vectors originate from the center of mass (usually we center the data as the first step)
- Principal component #1: points in the direction of the largest variance
- Each subsequent principal component:
– is orthogonal to the previous ones, and
– points in the directions of the largest variance of the residual subspace
49

---

## Page 51

## 9.2 PCA algorithms
Here we present 3 different algorithms for performing PCA.
Algorithm 18: (Sequential PCA)
Given centered data {x(1), x(2), . . . , x(m)}, compute the principal vectors:
w1 = arg max
‖w‖=1
1
m
m∑
i=1
(w
T x
(i))
2
w2 = arg max
‖w‖=1
1
m
m∑
i=1
(w
T (x
(i) − w1w
T
1 x
(i)))
2
. . .
wk = arg max
‖w‖=1
1
m
m∑
i=1
(w
T (x
(i) −
k−1∑
j=1
wj w
T
j x
(i)))
2
In the Sequential algorithm, to find w1, we maximize the variance of projection of x. To
find w2, we maximize the variance of the projection in the residual subspace.
The Sequential algorithm is intuitive and gives a sense of what to look for in a principal vector.
However, it is slow and not often used in practice unless we only care about the first principal
vector.
Algorithm 19: (Sample covariance matrix PCA)
Given data {x(1), x(2), . . . , x(m)}, compute covariance matrix
Σ =
1
m
m∑
i=1
(x
(i) − ¯x)(x
(i) − ¯x)
T
where ¯x =
1
m
∑m
i=1 x(i). The principal vectors are the eigenvectors of Σ, and larger eigenval-
ues corresponds to more important eigenvectors.
While straightforward, the computation of Σ and its eigenvectors is computationally expensive.
In practice, the most useful method is by singular value decomposition (SVD), which avoids
explicitly computing Σ.
50

---

## Page 52

Algorithm 20: (SVD PCA)
Perform SVD of the centered data matrix X = (x(1), . . . , x(m)) into
X = U SV
T
where U and V are orthonormal and S is a diagonal matrix. The columns of V are the
eigenvectors and the diagonal values of S - which are square roots of the eigenvectors of V -
denote the importance of each eigenvector in descending order. The top k principal vectors
are the columns of V T are the leftmost k columns of V .
Formally, the SVD of a matrix A is just the decomposition of A into three other matrices, which
we call U , S, and V . The dimensions of these matrices are given as subscripts in the formula
below:
An×m = Un×nSn×mV
T
m×m.
The columns of U are orthonormal eigenvectors of AAT . The columns of V are orthonormal
eigenvectors of AT A. The matrix S is diagonal, with the square roots of the eigenvalues from
U (or V ; the eigenvalues of AT A are the same as those of AAT ) in descending order. These
eigenvalues are called the singular values of A.
## 9.3 PCA applications
The main applications of PCA are:
- Data visualization - by reducing the number of dimensions to 2 or 3, we can plot the data
points on a graph
- Noise reduction, e.g. eigenfaces
- Data compression
## 9.3.1 Eigenfaces
We want to identify specific person, based on facial image, robust to glasses, lighting, facial
expression, ... (i.e., they are considered noise in this case). Each image is 256 × 256 pixels so
each input x is 2562 = 65536 dimensional.
Since the number of dimensions is too large, we cannot perform classification directly. Instead,
we use PCA on the whole dataset to get “principal component” images (the eigenfaces ), then
classify based on projection weights onto these principal component images.
51

---

## Page 53

Suppose there are m instances each with dimension N (in this case m = 50, , N = 65536). Given
a N × N covariance matrix Σ, can compute:
- All N eigenvectors / eigenvalues in O(N 3)
- First k eigenvectors / eigenvalues in O(kN 2)
But this is expensive if N = 65536. However, there is a clever workaround, since we note that
m  65536. Specifically, we first compute the eigenvectors v’s of L = X T X (which is much
smaller, only m × m), then for each v, Xv would be an eigenvector of X T X.
Diving in the Math 14 - Proof of workaround for eigenfaces
We want to prove that if v is eigenvector of L = X T X then Xv is eigenvector of Σ = XX T .
Based on the definition of eigenvector, there exists γ such that
Lv = γv
X
T Xv = γv
X(X
T Xv) = X(γv) = γXv
(XX
T )Xv = γ(Xv)
Σ(Xv) = γ(Xv)
Again, using the definition of eigenvector, we see that Xv is an eigenvector of Σ, also with
eigenvalue γ.
In other words, we do not have to compute the eigenvalues of Σ directly from Σ, but through
L. This would reduce the runtime to O(N m2) + O(km2), where k is the specified number of
eigenvectors (i.e., the number of dimensions we want to reduce to).
We can then reconstruct the faces using some of the top principal vector. As more eigenvectors
are used, we get back more detailed faces but without noises such as lighting, glasses and facial
expression. The below figures demonstrate we can reconstruct one particular face, starting from
using only one principal vectors, then adding more and more. The circled face denotes the best
approximation without noise.
52

---

## Page 54

Note: this method is quite old. Nowadays we use deep neural network.
## 9.3.2 Image compression
To compress an image, we can divide it in patches (12 × 12 pixels on a grid), so each patch is a
144-D vector input. Using PCA on these inputs, reconstructing the patches, then putting them
back together again will give us the compressed version. In some cases, using only 13 principal
vectors can already reduce the relative error to 5% (i.e., most information is in the top principal
vectors).
## 9.4 Shortcomings
PCA is unsupervised and doesn’t care about the labels. It maximizes the variance, independence
of class. For example, in the plot below, if we want to reduce the dimension to 1 while preserving
class separations, we would pick the green line. However, PCA would pick the magenta line
instead.
Furthermore, PCA can only capture linear relationships.
53

---

## Page 55

# Chapter 10
# Hidden Markov Model
## 10.1 Introduction
Definition 11: (Hidden Markov Model)
A Hidden Markov Model consists of the followings:
- A set of states S = {s1, s2, . . . , sn}. At each time t we are in exactly one of these
states, denoted by qt.
- A list π1, π2, . . . , πn where πi is the probability that we start at state i.
- A transition probability matrix Aj,i = P (qt = si | qt−1 = sj ), which denotes the
probability of transitioning from sj to si.
- A set of possible outputs Σ, at each time t we emit a symbol σt ∈ Σ.
- An emission probability matrix Bt,i = P (ot | si), which denotes the probability of
emitting symbol σt at state si.
For example, a two-state HMM may look like the followings:
Figure 10.1: An example Hidden Markov Model with 2 states.
Note the Markov property from the above definition: given qt, qt+1 is conditionally inde-
pendent on qt−1 or any earlier time point. In other words, knowing qt is sufficient to infer
about the state of qt+1.
With n states and m output symbols, we can see that there are n starting parameters πi, n2
transition probabilities Aji, and mn emission probabilities Bik, for a total of n2 + mn + n =
O(n2 + mn) parameters. We will discuss how to learn these parameters from data later on, but
let’s first focus on the inference task. Assuming all of these parameters are already known, what
kind of information can we infer?
54

---

## Page 56

## 10.2 Inference in HMM
There are three big questions that a learned HMM can answer:
1. What is P (qt = si)? In other words, what is the probability that we end up in state si at
time t, without observing any output ?
2. What is P (qt = si | o1o2 . . . ot)? In other words, given a sequence of output symbols
o1o2 . . . ot, what is the probability that we end up in state si at time t?
3. What is arg max
q1q2...qt
P (q1q2 . . . qt | o1o2 . . . ot)? In other words, given a sequence of output
symbols o1o2 . . . ot, what is the sequence of states q1q2 . . . qt that is most likely to generate
this output?
Before moving on, we show an example application of these questions. A popular technique of
modeling student knowledge in Educational Data Mining is called Bayesian Knowledge Tracing.
The high-level goal is: given data about the correctness of a student’s answers on a set of
problems related to a certain skill, can we say whether the student has mastered this skill?
55

---

## Page 57

Definition 12: (Bayesian Knowledge Tracing)
For each skill, BKT models student knowledge as a binary latent variable in an HMM ,
which consists of the followings:
- Two states: S = {Mastered, Unmastered}.
- πMastered: the probability of the student starting at Mastered, i.e., knowing the skill
beforehand.
- pLearn: the probability of transitioning from Unmastered to Mastered. pForget: the
probability of transitioning from Mastered to Unmastered.
- Two possible outputs C (correct) and I (incorrect): whether student’s answer to a
problem is correct or incorrect.
- pGuess = p(ot = C | qt = Unmastered): the probability of getting a correct answer
despite not mastering the skill, i.e., guessing.
- pSlip = p(ot = I | qt = Mastered): the probability of getting an incorrect answer
despite mastering the skill, i.e., slipping.
Mastered Unmastered
C I
pForget
1 − pForget
pLearn
1 − pLearn
1 − pGuess
pSlip pGuess
1 − pSlip
Using Inference #2, we can ask questions like: if the student submits 5 answers and gets the
first 3 correct but last 2 incorrect, what is the probability that she has mastered the skill? More
formally, what is P (Mastered | CCCII)? Is this different from, for example, P (Mastered | IICCC)
(getting first 2 incorrect but last 3 correct)?
## 10.2.1 What is P (qt = si)?
Since we don’t have observed data, the emission probabilities can be ignored. Instead, we simply
rely on the priors and transition probabilities. For example, in Figure 10.1 we can compute
P (q2 = A) as
P (q2 = A) = P (q2 = A | q1 = A) · p(q1 = A) + p(q2 = A | q1 = B) · p(q1 = B)
= AAA · πA + ABA · πB ,
56

---

## Page 58

and then P (q3 = B) as
P (q3 = B) = P (q3 = B | q2 = A) · p(q2 = A) + P (q3 = B | q2 = B) · p(q2 = B)
= AAB · (AAA · πA + ABA · πB ) + ABB · (AAB · πA + ABB · πB ).
In general,
P (qt = si) =
∑
q1,q2,...,qt−1∈S
P (si | q1q2 . . . qt−1)P (q1q2 . . . qt−1). (10.1)
However, this is too costly to compute, with runtime O(2n−1). Instead, an optimization trick is
to use dynamic programming:
Algorithm 21: (Computing final state without observations)
We perform two steps:
- Base case: P (q1 = si) = πi
- Inductive case:
P (qt+1 = si) =
∑
j∈S
P (qt+1 = si | qt = sj ) · P (qt = sj ) =
∑
j∈S
Aji · P (qt = sj ). (10.2)
## 10.2.2 What is P (qt = si | o1o2 . . . ot)?
Using the chain rule, we first see that
P (qt = si | o1o2 . . . ot) =
P (qt = si ∧ o1o2 . . . ot)
P (o1o2 . . . ot)
=
P (qt = si ∧ o1o2 . . . ot)
∑
j∈S
P (qt = sj ∧ o1o2 . . . ot)
(10.3)
This motivates us to define αt(i) = P (qt = si ∧ o1o2 . . . ot). We can then compute αt(i) as follows.
Algorithm 22: (Computing final state given observed output sequence)
To compute αt(i), we perform two steps:
- Base case: α1(i) = P (q1 = si ∧ o1) = P (o1 | q1 = s1)P (q1 = s1) = B1,i · πi.
- Inductive case:
αt+1(i) =
∑
j∈S
αt(j) · Aj,i · Bt+1,i. (10.4)
It follows that
P (qt = si | o1o2 . . . ot) =
αt(i)
∑
j∈S
αt(j)
(10.5)
## 10.2.3 What is arg max
q1q2...qt
## P (q1q2 . . . qt | o1o2 . . . ot)?
Let
δt(i) = max
q1,...,qt−1∈S
P (q1 . . . qt−1 ∧ qt = si ∧ o1 . . . ot). (10.6)
In other words, δt(i) is the probability of the most likely path from time 1 to t that produces
output o1 . . . ot and ends in si. We can then compute δt(i) as follows.
57

---

## Page 59

Algorithm 23: (Viterbi Algorithm)
We perform two steps:
- Base case: δ1(i) = πi · B1,i.
- Inductive case:
δt+1(i) = max
j
δt(i) · Aj,i · Bt+1,i. (10.7)
It follows that arg max
q1q2...qt
P (q1q2 . . . qt | o1o2 . . . ot) is the path defined by arg max
j
δt(j).
58

---

## Page 60

# Chapter 11
# Reinforcement Learning
## 11.1 Markov decision process
A Markov decision process is a set of nodes and edges where nodes represent states and edges
represent transition. In this case, the transitions are only based on the previous state (same as
in HMM). Unlike HMM, however:
- We know all the states, each state associated with a reward.
- We can have an influence on the transition.
An obvious question for such models: what is the combined expected value for each state? What
can we expect to earn over our lifetime if we become asst. prof / go to industry? Before we
answer this quesiton, we need to define a model for future rewards. In particular, the value of a
current award is higher than the value of future awards (inflation, confidence). This discounted
reward model is specified using a parameter 0 < γ < 1. Therefore, if we let rt be the reward at
time t, then the total reward is
Total =
∞∑
t=0
γ
trt, (11.1)
59

---

## Page 61

which does converge because γ ∈ (0, 1).
Now, let’s define J ∗(si) as the expected discounted sum of rewards when starting at state si. It
follows that
J
∗(si) = ri + γ
n∑
k=1
pikJ
∗(sk), (11.2)
where pik is the transition probability from si to sk and the sum represents the expected pay for
all possible transitions from si.
We have n equations like (11.2), one for each si, so this is a linear system of equations and
a closed form solution can be derived, but may be time consuming. It also doesn’t generalize
to non-linear models. Alternatively, this problem can be solved in an iterative manner: define
J t(si) as the expected discounted reward after t steps, then J 1(si) = ri and
J
t+1(si) = ri + γ
∑
k
pikJ
t(sk). (11.3)
This can be computed via dynamic programming, and we can stop when max
i
|J
t+1(si)−J
t(si)| <
 for some threshold , which we know will happen because J t(si) converges.
## 11.2 Reinforcement learning - No action
In reinforcement learning, we use the same Markov model with rewards and actions. But there
are a few differences:
1. We do not assume we know the Markov model
60

---

## Page 62

2. We adapt to new observation (online vs offline)
In other words, we want to learn the expected reward but do not know the model, and in this
case we do so by learning both the reward and model at the same time (e.g., game playing, robot
interacting with environment). Unlike HMM, if we move to a state, we know which state that is
(i.e., the states are observed); other than that, however, we don’t know the reward at that state
or the transition probabilities.
## 11.2.1 Supervised RL
More formally, we define the scenario in reinforcement learning as follows: we are wandering the
world, and at each time point we see a state and a reward. Our goal is to compute the sum of
discounted rewards for each state J est(si). For example, given the following observations
s1, 4 s2, 0 s3, 2 s2, 2 s4, 0
In general, we have the supervised learning algorithm for RL as follows.
Algorithm 24: (Supervised reinforcement learning)
Observe set of states and rewards (s(0), r(0)), (s(1), r(1)), . . . , (s(T ), r(T )).
For t = 0, . . . , T compute discounted sum
J (t) =
T∑
i=t
γ
i−tr(i).
Compute J est(si) (mean of J (t) for t such that s(t) = si):
J
est(si) =
∑T
t=0 J (t)I (s(t) = si)
∑T
t=0 I (s(t) = si)
.
Here we assume that we observe each state frequently enough and that we have many observa-
tions so that the final observations do not have a big impact on our prediction. Each update
takes O(n) where n is the number of states, since we are updating vectors containing entries for
all states. Space is also O(n). Convergence to J ∗ can be proven, and the algorithm can be more
efficient by ignoring states for which discounted factor γ i is very low already.
However, the supervised learning approach has two problems:
61

---

## Page 63

- Takes a long time to converge, because we don’t try to learn the underlying MDP model,
but just focus on J est.
- Does not use all available data, we can learn transition probabilities as well.
In other words, we want to utilize the fact that there is an underlying model and the transitions
are not completely random.
## 11.2.2 Certainty-Equivalence learning
Algorithm 25: (Certainty-Equivalence (CE) learning)
We keep track of 3 vectors:
- Count(s): number of times we visited state s
- J (s): sum of rewards from state s
- T rans(i, j): number of time we transitioned from si to sj
When we visit state si, receive reward r and move to state sj we do the following:
- Counts(si) = Counts(si) + 1
- J (si) = J (si) + r
- T rans(i, j) = T rans(i, j) + 1
At any time, we can estimate:
- Reward estimate rest(s) = J (s)/Counts(s)
- Transition probability estimate
- pest(j | i) = T rans(i, j)/Counts(si)
After learning the model, we can now have an estimate which we can solve for all states si:
J
est(si) = r
est(si) + γ
∑
j
p
est(sj | si)J
est(si), i = 1, . . . , n (11.4)
62

---

## Page 64

The runtime of CE comes from two steps: update (O(1)) and solving MDP (O(n3) using matrix
inversion). The space is O(n2) for transition probabilities.
To reduce runtime, we could use the “One backup” version, which updates J est(si) for the current
state si while learning the model, instead of solving n equations after learning like in (11.4). In
this case, the runtime is only O(n), and we can sill prove convergence to J ∗ (but slower than
CE). The space remains at O(n2).
## 11.2.3 Temporal difference learning
We now look at another algorithm with the same efficiency as one backup CE but requires much
less space. In particular, we can ignore all the rest and pest and only focus on J est with a new
approximation rule.
Algorithm 26: (Temporal difference (TD) learning)
We only maintain the J est array. Assume we have J est(s1), . . . , J est(sn). If we observe a
transition from state si to state sj and a reward r, we update using the following rule
J
est(si) = (1 − α)J
est(si) + α(r + γJ
est(sj )), (11.5)
where α is a hyper-parameter to determine how much weight we place on the current obser-
vation (and can change during the algorithm, unlike γ).
As always, choosing a good α is an issue. Nevertheless, it can be proven that TD learning is
guaranteed to converge if:
- All states are visited often.
•
∑
t αt = ∞
•
∑
t α2
t < ∞
63

---

## Page 65

For example, αt =
C
t for some constant t would satisfy both requirements.
Now the runtime of TD is O(1) because there is only one update (11.5) at each iteration, and
the space is O(n) because of the J est array.
Here is a summary so far of the four reinforcement learning algorithms.
Method Time Space
Supervised learning O(n) O(n)
CE learning O(n3) O(n2)
One backup CE O(n) O(n2)
TD learning O(1) O(n)
## 11.3 Reinforcement learning with action - Policy learning
So far we assumed that we cannot impact the outcome transition. In real world situations we
often have a choice of actions we take (as we discussed for MDPs). How can we learn the best
policy for such cases?
Note the difference in the pest table - while the columns are still the states (because we only
transition from state to state), the rows are now (state, action) pair, because each action leads
to a different transition. Our goal is to learn the action that leads to the most reward. In
particular, we can update CE by setting
J
est(si) = r
est(si) + max
a
(
γ
∑
j
p
est(sj | si, a)J
est(sj )
)
. (11.6)
As mentioned above, we can also use TD learning for better efficiency. However, TD is model
free, so in this context, we can adjust TD to learn policies by defining Q∗(si, a) = expected sum
64

---

## Page 66

of future (discounted) rewards if we start at state si and take action a. Then, when we take a
specific action a in state si and then transition to state sj we can update
Q
est(si, a) = (1 − α)Q
est(si, a) + α(ri + γ max
a′ Q
est(sj , a
′)). (11.7)
Instead of the J est vector we maintain the Qest matrix, which is a rather sparse n by m matrix
(n states and m actions).
In practice, when choosing the next action, we may not necessarily pick the one that results in
the highest expected sum of future rewards, because we are only sampling from the distribution
of possible outcomes. We do not want to avoid potentially beneficial actions. Instead, we can
take a more probabilistic approach
p(a) =
1
Z
exp
(
−
Qest(si, a)
f (t)
)
, (11.8)
where Z is a normalizing constant and f (t) decreases as time t goes by, to represent that we
are more confident in the learned model. We can initialize Q values to be high to increase the
likelihood that we will explore more options. Finally, it can be shown that Q learning converges
to optimal policy.
65

---

## Page 67

# Chapter 12
# Generalization and Model Selection
## 12.1 True risk vs Empirical risk
Definition 13: (True risk)
True risk is the target performance measure. It is defined as is the probability of misclassifi-
cation P (f (X) 6 = Y ) in classification and mean squared error E[(f (X) − Y )2] in regression.
More generally, it is the expected performance on a random test point (X, Y ).
While we want to minimize true risk, we do not know that the underlying distribution of X and
Y is. What we do know are the samples (Xi, Yi), which give us the empirical risk.
Definition 14: (Empirical risk)
Empirical risk is the performance on training data. It is defined as proportion of misclassified
examples
1
n
∑n
i=1 I (f (Xi) 6 = Yi) in classification and average squared error
1
n
∑n
i=1(f (Xi) −
Yi)2 in regression.
So we want to minimize the empirical risk and evaluate the true risk, but this may lead to
overfitting (i.e., small training error but large generalization error). For instance, the following
graph shows two classifiers for a binary classification problem (football player or not). While
the classifier on the right has zero training error, we are much less inclined to believe that it
captures the true distribution. Here it is more likely that football players simply have higher
height and weight, which match better with the classifier on the left.
The question is: when should we not minimize the empirical risk completely? The following
graph shows what the empirical risk and true risk may look like as we increase the model
complexity. Initially both types of risk would decrease, but after some point (the Best Model
66

---

## Page 68

point), we started fitting the noise instead of the true data. In that case, the empirical risk can
keep decreasing while the true risk increases.
Again, we do not know how true risk in practice, which makes this a difficult problem. Can we
estimate the true risk in a way better than just using the empirical risk? One way is to use
structural risk minimization.
Definition 15: (Structural risk minimization)
Penalize models using bound on deviation of true and empirical risk
ˆfn = arg min
f ∈F
{ ˆRn(f ) + λC(f )}, (12.1)
where λ is a tuning parameter chosen by model selection, and C(f ) is the bound on deviation
from true risk a. In essence, instead of minimizing the unknown true risk directly, we try to
minimize an upper bound (with high probability) on the true risk.
aWe will discuss how to derive these later.
In other words, we penalize models based on prior information (bias) or information criteria
(MDL, AIC, BIC). In ML there is a “no free lunch” theorem: given only the data, we cannot
learn anything. We need some kind of prior information (inductive bias); for example, in using
linear regression, our inductive bias is that the data can be fit by a line. The inductive bias
in this case, also called Occam’s Razor, is to seek the simplest explanation (e.g., if a 10-degree
67

---

## Page 69

polynomial and 100-degree polynomial say roughly the same things, pick the former).
Inductive bias can also come from domain knowledge. For example, the function of oil spill
contamination should be smooth (if one point is contaminated, the points around it should be
as well), while the function of photon arrival is not. Therefore, even if we get the same data,
the fit functions may look very different.
An example of penalizing complex models using prior knowledge is regularized linear regres-
sion, which uses some norm of regression coefficients as the cost C(f ). An example of penal-
izing models based on information content is AIC (C(f ) = # parameters) or BIC (C(f ) =
# parameters × log n). AIC allows # parameters to be infinite as # of training data n becomes
large, while BIC penalizes complex models more heavily.
## 12.2 Model Selection
68
