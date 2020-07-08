# Example of interactive jobs config

1. Make sure that `neuro-flow` is installed: `pip install -e .` from the project's root.

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
neuro-flow upload-all
```

5. Run jobs

Notebook:
```
neuro-flow run jupyter
```

Train:
```
neuro-flow run train
```

6. List jobs

```
neuro-flow ps
```

6. Kill job

```
neuro-flow kill jupyter
```

7. Show logs

```
neuro-flow logs jupyter
```


8. Get extended status

```
neuro-flow status train
```
