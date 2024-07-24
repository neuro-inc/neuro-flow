# Example of interactive jobs config

1. Make sure that the `apolo-flow` package is installed: `pip install -U apolo-flow`.

2. Change current dir to this or any nested folder:

```
cd examples/demo-jobs
```

3. Create remote directories:
```
apolo-flow mkvolumes
```

4. Upload data to storage:
```
apolo-flow upload ALL
```

5. Build image (Warning: this operation takes a lot of time, please be patient):
```
apolo-flow build img
```

6. Run jobs

Jupyter Notebooks:
```
apolo-flow run jupyter
```

Train:
```
apolo-flow run train
```

Multitrain (several instances of this job can be executed on parallel):
```
apolo-flow run multitrain -s bert -- --model bert
```
* Use `-s` to provide a custom suffix (otherwise a generated suffix is assigned).
* Pass additional parameters after `--`.

7. List jobs

```
apolo-flow ps
```

8. Kill job

```
apolo-flow kill jupyter
```

9. Show logs

```
apolo-flow logs jupyter
apolo-flow logs multitrain bert
```


10. Get extended status

```
apolo-flow status train
```
