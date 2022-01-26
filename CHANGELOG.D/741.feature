Add support of expressions in matrix definition.

You can now use expression to define list of matrix products. In examples here and below,
both `old_way_key` and `new_way_key` produce same list of values:

```
matrix:
  old_way_key: ["1", "2", "3"]
  new_way_key: ${{ ["1", "2", "3"] }}
```

This can be helpful when used together with new `range()` function:

```
matrix:
  old_way_key: [0, 1, 2, 3]
  new_way_key: ${{ range(4) }}
```

The `range()` function supports same parameters as python's `range()`, but it returns list.
For example: `${{ range(1, 4) }}` generates `[1,2,3]`, and `${{ range(4, 1, -1) }}` generates
`[4,3,2]`.

As sometimes plain numbers is not best options for matrix products, you can use list comprehension
to perform some mapping:

```
matrix:
  old_way_key: ["k1", "k2", "k3"]
  new_way_key: ${{ [fmt("k{}", str(it)) for it in range(1, 4)] }}
```

You can also filter some values in comprehension same way as in python:

```
matrix:
  old_way_key: [0, 4, 16]
  new_way_key: ${{ [it * it for it in range(1, 5) if it % 2 == 0] }}
```
