"""Independent forward-pass check for the portable NumPy decision head."""
import unittest
import numpy as np
import torch
from physics_rsi import predict as torch_predict
from physics_rsi_cpu import predict


class PortableTests(unittest.TestCase):
    def test_scores_and_choices_match_tensor_implementation(self):
        # Verify FP32 algebra, independently of platform-default TF32 kernels.
        torch.set_float32_matmul_precision('highest')
        torch.backends.cuda.matmul.allow_tf32=False
        rng=np.random.default_rng(100)
        w=dict(mean=rng.normal(size=29),scale=rng.uniform(.2,2,size=29))
        state={}
        for layer,inputs,outputs in [(0,32,64),(2,64,64),(4,64,2)]:
            w[f'w{layer}']=rng.normal(0,.1,(outputs,inputs)).astype(np.float32)
            w[f'b{layer}']=rng.normal(0,.1,outputs).astype(np.float32)
            state[f'{layer}.weight']=torch.from_numpy(w[f'w{layer}'])
            state[f'{layer}.bias']=torch.from_numpy(w[f'b{layer}'])
        x=rng.normal(size=(120,29)).astype(np.float32)
        x[:,4]=.08
        expected=torch_predict(dict(state_dict=state,mean=w['mean'].tolist(),scale=w['scale'].tolist()),x)
        actual=predict(x,w)
        np.testing.assert_allclose(actual,expected,atol=5e-7,rtol=1e-6)
        np.testing.assert_array_equal(actual.argmin(1),expected.argmin(1))


if __name__=='__main__':
    unittest.main()
