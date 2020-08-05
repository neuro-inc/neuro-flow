# Example of interactive jobs config

1. Make sure that the `neuro-extras` package is installed: clone https://github.com/neuromation/neuro-extras and `pip install -e .` from that project's root.

2. Make sure that the `neuro-flow` package is installed: `pip install -e .` from this project's root.

3. Change current dir to this or any nested folder:

```
cd examples/demo-jobs
```

4. Create remote directories:
```
neuro-flow mkvolumes
```

4. Upload data to storage:
```
neuro-flow upload ALL
```

5. Build image (Warning: this operation takes a lot of time, please be patient):
```
neuro-flow build img
```

6. Run jobs

Jupyter Notebooks:
```
neuro-flow run jupyter
```

Train:
```
neuro-flow run train
```

7. List jobs

```
neuro-flow ps
```

8. Kill job

```
neuro-flow kill jupyter
```

9. Show logs

```
neuro-flow logs jupyter
```


10. Get extended status

```
neuro-flow status train
```
