# Example of interactive jobs config

1. Make sure that the `neuro-flow` package is installed: `pip install -U neuro-flow`.

2. Change current dir to this or any nested folder:

```
cd examples/demo-jobs
```

3. Create remote directories:
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

Multitrain (several instances of this job can be executed on parallel):
```
neuro-flow run multitrain -s bert -- --model bert 
```
* Use `-s` to provide a custom suffix (otherwise a generated suffix is assigned).
* Pass additional parameters after `--`.

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
neuro-flow logs multitrain bert
```


10. Get extended status

```
neuro-flow status train
```

# Examples of batch configs 

Minimalistic batches:

```
neuro-flow bake seq
neuro-flow bake matrix
```

A batch with non-linear DAG with 7 tasks:

```
neuro-flow build numpy
neuro-flow bake demo
```
