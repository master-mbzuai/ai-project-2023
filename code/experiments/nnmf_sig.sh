#args=("25" "50" "75" "90")
args=("25" "50" "75" "90")
geometry_settings=("80x24+0+0" "80x24+400+0" "80x24+0+400" "80x24+400+400" "80x24+0+800" "80x24+400+800")

cd ..
for i in "${!args[@]}"; do
  geometry=${geometry_settings[$i % ${#geometry_settings[@]}]}
  xterm -geometry $geometry -e "python main.py --d ${args[$i]} --model_name nnmf_sig --epochs 50 --experiment_name nnmf_sig --lr 0.0001; exit" &  
done

#xterm -e "python main.py --d 0 --model_name nnmf_base --epochs 100 --experiment_name nnmf_base --lr 0.0001; exit" &  
