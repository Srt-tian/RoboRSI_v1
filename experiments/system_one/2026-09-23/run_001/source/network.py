"""Small reproducible NumPy MLP with Adam; no pretrained or language weights."""

import numpy as np


def sigmoid(x):
    return 1/(1+np.exp(-np.clip(x, -40, 40)))


class DecisionNet:
    def __init__(self, inputs, hidden=64, *, kind="outcome", seed=0):
        if kind not in ("outcome", "paired", "choice"):
            raise ValueError("unknown model kind")
        self.kind = kind
        self.hidden = hidden
        self.mean = np.zeros(inputs)
        self.scale = np.ones(inputs)
        rng = np.random.default_rng(seed)
        outputs = 5 if kind == "paired" else 3
        self.params = {
            "w1": rng.normal(0, np.sqrt(2/inputs), (inputs, hidden)), "b1": np.zeros(hidden),
            "w2": rng.normal(0, np.sqrt(2/hidden), (hidden, hidden)), "b2": np.zeros(hidden),
            "w3": rng.normal(0, np.sqrt(1/hidden), (hidden, outputs)), "b3": np.zeros(outputs),
        }

    def fit_scaler(self, x):
        self.mean = x.mean(axis=0)
        self.scale = np.maximum(x.std(axis=0), 1e-5)

    def forward(self, x, *, cache=False):
        z = (np.asarray(x)-self.mean)/self.scale
        h1 = np.tanh(z@self.params["w1"]+self.params["b1"])
        h2 = np.tanh(h1@self.params["w2"]+self.params["b2"])
        logits = h2@self.params["w3"]+self.params["b3"]
        if self.kind == "choice":
            exp = np.exp(logits-logits.max(axis=1, keepdims=True))
            prediction = exp/exp.sum(axis=1, keepdims=True)
        else:
            prediction = sigmoid(logits)
        return (prediction, (z, h1, h2)) if cache else prediction

    def loss_grad(self, x, y):
        prediction, (z, h1, h2) = self.forward(x, cache=True)
        if self.kind == "paired":
            p0 = y[:, 0]
            weight = np.column_stack((np.ones(len(y)), 1-p0, p0, 1-p0, p0))
            target = y/np.maximum(weight, 1e-10)
        else:
            weight, target = np.ones_like(y), y
        bounded = np.clip(prediction, 1e-9, 1-1e-9)
        if self.kind == "choice":
            loss = -(target*np.log(bounded)).sum()/len(y)
            delta = (prediction-target)/len(y)
        else:
            loss = -(weight*(target*np.log(bounded)+(1-target)*np.log(1-bounded))).sum()/len(y)
            delta = weight*(prediction-target)/len(y)
        gradients = {"w3": h2.T@delta, "b3": delta.sum(axis=0)}
        d2 = (delta@self.params["w3"].T)*(1-h2*h2)
        gradients.update(w2=h1.T@d2, b2=d2.sum(axis=0))
        d1 = (d2@self.params["w2"].T)*(1-h1*h1)
        gradients.update(w1=z.T@d1, b1=d1.sum(axis=0))
        return float(loss), gradients

    def success(self, x):
        p = self.forward(x)
        if self.kind == "paired":
            p0 = p[:, 0]
            return np.column_stack((p0, (1-p0)*p[:, 1]+p0*(1-p[:, 2]), (1-p0)*p[:, 3]+p0*(1-p[:, 4])))
        if self.kind == "choice":
            raise ValueError("choice probability is not task success probability")
        return p

    def rescue_spoil(self, x):
        if self.kind != "paired":
            raise ValueError("joint heads required")
        p = self.forward(x)
        return np.column_stack(((1-p[:, 0])*p[:, 1], p[:, 0]*p[:, 2], (1-p[:, 0])*p[:, 3], p[:, 0]*p[:, 4]))

    def save(self, path):
        np.savez_compressed(path, **self.params, mean=self.mean, scale=self.scale, kind=np.asarray(self.kind), hidden=np.asarray(self.hidden))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            model = cls(len(data["mean"]), int(data["hidden"]), kind=str(data["kind"]))
            model.params = {key: data[key].copy() for key in model.params}
            model.mean, model.scale = data["mean"].copy(), data["scale"].copy()
        return model


def train(model, x, y, *, epochs, seed, callback, learning_rate=0.002, batch_size=256):
    model.fit_scaler(x)
    rng = np.random.default_rng(seed)
    first = {k: np.zeros_like(v) for k, v in model.params.items()}
    second = {k: np.zeros_like(v) for k, v in model.params.items()}
    step = 0
    for epoch in range(1, epochs+1):
        order = rng.permutation(len(x))
        total_loss = 0.0
        for start in range(0, len(x), batch_size):
            ix = order[start:start+batch_size]
            loss, gradients = model.loss_grad(x[ix], y[ix])
            total_loss += loss*len(ix)
            step += 1
            for key, gradient in gradients.items():
                first[key] = 0.9*first[key]+0.1*gradient
                second[key] = 0.999*second[key]+0.001*gradient**2
                m, v = first[key]/(1-0.9**step), second[key]/(1-0.999**step)
                model.params[key] -= learning_rate*m/(np.sqrt(v)+1e-8)
        callback(epoch, total_loss/len(x), model)
